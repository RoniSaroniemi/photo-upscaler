#!/usr/bin/env python3
"""
Read local ActivityWatch presence data for agent decision support.

This tool is intentionally read-only. It queries the local ActivityWatch HTTP API
and summarizes the AFK watcher bucket into a compact presence snapshot.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:5600"
NOW_TOLERANCE_SECONDS = 5


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def format_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def build_url(base_url: str, path: str, params: dict[str, str] | None = None) -> str:
    root = base_url.rstrip("/")
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    return f"{root}/api/0{path}{query}"


def fetch_json(base_url: str, path: str, params: dict[str, str] | None = None) -> Any:
    url = build_url(base_url, path, params)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = f"ActivityWatch API error {exc.code} for {url}"
        if detail:
            message = f"{message}: {detail}"
        raise SystemExit(message) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach ActivityWatch at {base_url}: {exc.reason}") from exc


def get_info(base_url: str) -> dict[str, Any]:
    payload = fetch_json(base_url, "/info")
    if not isinstance(payload, dict):
        raise SystemExit("Invalid /info response from ActivityWatch")
    return payload


def get_buckets(base_url: str) -> dict[str, Any]:
    payload = fetch_json(base_url, "/buckets/")
    if not isinstance(payload, dict):
        raise SystemExit("Invalid /buckets/ response from ActivityWatch")
    return payload


def detect_bucket(base_url: str) -> dict[str, Any]:
    info = get_info(base_url)
    hostname = info.get("hostname")
    buckets = get_buckets(base_url)
    candidates: list[dict[str, Any]] = []
    for bucket_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        if bucket.get("type") != "afkstatus":
            continue
        entry = dict(bucket)
        entry["id"] = bucket_id
        candidates.append(entry)
    if not candidates:
        raise SystemExit("No ActivityWatch afkstatus bucket found")

    def score(item: dict[str, Any]) -> tuple[int, int, str]:
        return (
            1 if item.get("client") == "aw-watcher-afk" else 0,
            1 if hostname and item.get("hostname") == hostname else 0,
            item["id"],
        )

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def get_events(
    base_url: str,
    bucket_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {}
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat()
    if limit is not None:
        params["limit"] = str(limit)
    payload = fetch_json(base_url, f"/buckets/{bucket_id}/events", params)
    if not isinstance(payload, list):
        raise SystemExit(f"Invalid events response for bucket {bucket_id}")
    events: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            events.append(item)
    return events


def event_bounds(event: dict[str, Any]) -> tuple[datetime, datetime]:
    start = parse_iso(str(event["timestamp"]))
    duration = float(event.get("duration", 0))
    return start, start + timedelta(seconds=duration)


def latest_active_boundary(latest_event: dict[str, Any], now: datetime) -> datetime | None:
    start, end = event_bounds(latest_event)
    status = latest_event.get("data", {}).get("status")
    if status == "afk":
        return start
    if status == "not-afk":
        return min(end, now)
    return None


def lookback_totals(events: list[dict[str, Any]]) -> tuple[float, float]:
    active_seconds = 0.0
    afk_seconds = 0.0
    for event in events:
        duration = float(event.get("duration", 0))
        status = event.get("data", {}).get("status")
        if status == "not-afk":
            active_seconds += duration
        elif status == "afk":
            afk_seconds += duration
    return active_seconds, afk_seconds


def resolve_bucket(base_url: str, explicit_bucket_id: str | None) -> tuple[str, dict[str, Any]]:
    if explicit_bucket_id:
        buckets = get_buckets(base_url)
        bucket = buckets.get(explicit_bucket_id)
        if not isinstance(bucket, dict):
            raise SystemExit(f"Bucket {explicit_bucket_id!r} not found")
        entry = dict(bucket)
        entry["id"] = explicit_bucket_id
        return explicit_bucket_id, entry
    bucket = detect_bucket(base_url)
    return str(bucket["id"]), bucket


def presence_snapshot(base_url: str, bucket_id: str, minutes: int) -> dict[str, Any]:
    latest_events = get_events(base_url, bucket_id, limit=1)
    if not latest_events:
        raise SystemExit(f"Bucket {bucket_id!r} has no events")
    latest = latest_events[0]
    now = now_utc()
    window_start = now - timedelta(minutes=minutes)
    window_events = get_events(
        base_url,
        bucket_id,
        start=window_start,
        end=now,
        limit=max(100, minutes * 4),
    )
    active_seconds, afk_seconds = lookback_totals(window_events)
    start, end = event_bounds(latest)
    status = latest.get("data", {}).get("status")
    is_active_now = bool(
        status == "not-afk" and end >= now - timedelta(seconds=NOW_TOLERANCE_SECONDS)
    )
    last_active = latest_active_boundary(latest, now)
    return {
        "is_active_now": is_active_now,
        "current_status": status,
        "status_since": format_iso(start),
        "last_seen_active_at": format_iso(last_active) if last_active else None,
        "active_seconds": round(active_seconds, 3),
        "afk_seconds": round(afk_seconds, 3),
        "lookback_minutes": minutes,
        "bucket_id": bucket_id,
    }


def history_summary(base_url: str, bucket_id: str, minutes: int) -> dict[str, Any]:
    now = now_utc()
    start = now - timedelta(minutes=minutes)
    events = get_events(
        base_url,
        bucket_id,
        start=start,
        end=now,
        limit=max(100, minutes * 4),
    )
    active_seconds, afk_seconds = lookback_totals(events)
    return {
        "bucket_id": bucket_id,
        "lookback_minutes": minutes,
        "window_start": format_iso(start),
        "window_end": format_iso(now),
        "active_seconds": round(active_seconds, 3),
        "afk_seconds": round(afk_seconds, 3),
        "event_count": len(events),
    }


def emit(args: argparse.Namespace, payload: Any, *, default_plain: str | None = None) -> int:
    if getattr(args, "json", False):
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if default_plain is not None:
        print(default_plain)
        return 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}={value}")
        return 0
    print(payload)
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    bucket = detect_bucket(args.base_url)
    payload = {
        "bucket_id": bucket["id"],
        "type": bucket.get("type"),
        "client": bucket.get("client"),
        "hostname": bucket.get("hostname"),
    }
    return emit(args, payload)


def cmd_status(args: argparse.Namespace) -> int:
    bucket_id, _bucket = resolve_bucket(args.base_url, args.bucket_id)
    payload = presence_snapshot(args.base_url, bucket_id, args.minutes)
    return emit(args, payload)


def cmd_history(args: argparse.Namespace) -> int:
    bucket_id, _bucket = resolve_bucket(args.base_url, args.bucket_id)
    payload = history_summary(args.base_url, bucket_id, args.minutes)
    return emit(args, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read ActivityWatch presence data")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--bucket-id")
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="Find the default AFK bucket")
    detect_parser.set_defaults(func=cmd_detect)

    status_parser = subparsers.add_parser("status", help="Show current presence summary")
    status_parser.add_argument("--minutes", type=int, default=15)
    status_parser.set_defaults(func=cmd_status)

    history_parser = subparsers.add_parser("history", help="Summarize AFK vs active over a window")
    history_parser.add_argument("--minutes", type=int, default=15)
    history_parser.set_defaults(func=cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
