#!/usr/bin/env python3
"""Metrics reporter — reads JSONL time-series and produces markdown reports.

Usage:
    python3 tools/metrics_report.py --date today
    python3 tools/metrics_report.py --date 2026-03-28
    python3 tools/metrics_report.py --range 7d
    python3 tools/metrics_report.py --date today --output .cpo/advisor/metrics-report.md
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
METRICS_DIR = os.path.join(PROJECT_DIR, "state", "metrics")

# Thresholds from strategic objectives
TARGET_IDLE_HOURS = 2.0
TARGET_STALL_RATE_PCT = 5.0


def _resolve_dates(date_str=None, range_str=None):
    """Resolve --date or --range into a list of date strings (YYYY-MM-DD)."""
    today = datetime.now(timezone.utc).date()
    if date_str:
        if date_str == "today":
            return [today.isoformat()]
        return [date_str]
    if range_str:
        # Parse "7d", "30d", etc.
        days = int(range_str.rstrip("d"))
        return [(today - timedelta(days=i)).isoformat() for i in range(days)]
    return [today.isoformat()]


def _load_jsonl(filepath):
    """Load a JSONL file, returning list of dicts. Returns [] if missing."""
    records = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except FileNotFoundError:
        pass
    return records


def _load_session_metrics(dates):
    """Load session metrics for given dates."""
    records = []
    for d in dates:
        path = os.path.join(METRICS_DIR, f"sessions-{d}.jsonl")
        records.extend(_load_jsonl(path))
    return records


def _load_agent_metrics(dates):
    """Load agent lifecycle metrics for given dates."""
    records = []
    for d in dates:
        path = os.path.join(METRICS_DIR, f"agents-{d}.jsonl")
        records.extend(_load_jsonl(path))
    return records


def _compute_idle_report(session_records):
    """Compute idle time metrics from session observations."""
    if not session_records:
        return None

    total_obs = len(session_records)
    idle_obs = sum(1 for r in session_records if r.get("status") == "idle")
    stalled_obs = sum(1 for r in session_records if r.get("status") == "stalled")
    active_obs = sum(1 for r in session_records if r.get("status") == "active")

    # Estimate total idle time: each observation represents ~poll_interval seconds
    # Group by timestamp to find poll intervals
    timestamps = sorted(set(r.get("ts", "") for r in session_records))
    if len(timestamps) >= 2:
        # Estimate poll interval from median gap between consecutive timestamps
        gaps = []
        for i in range(1, min(len(timestamps), 20)):
            try:
                t1 = datetime.strptime(timestamps[i - 1], "%Y-%m-%dT%H:%M:%SZ")
                t2 = datetime.strptime(timestamps[i], "%Y-%m-%dT%H:%M:%SZ")
                gaps.append((t2 - t1).total_seconds())
            except (ValueError, TypeError):
                continue
        poll_interval = sorted(gaps)[len(gaps) // 2] if gaps else 30
    else:
        poll_interval = 30

    # Each idle/stalled observation ≈ poll_interval seconds of idle time
    total_idle_seconds = (idle_obs + stalled_obs) * poll_interval
    total_idle_hours = total_idle_seconds / 3600

    # Find longest idle stretch per session
    longest_stretch = _find_longest_idle_stretch(session_records, poll_interval)

    return {
        "total_obs": total_obs,
        "active_obs": active_obs,
        "idle_obs": idle_obs,
        "stalled_obs": stalled_obs,
        "total_idle_hours": round(total_idle_hours, 1),
        "meets_target": total_idle_hours < TARGET_IDLE_HOURS,
        "longest_stretch": longest_stretch,
    }


def _find_longest_idle_stretch(records, poll_interval):
    """Find the longest continuous idle/stalled stretch."""
    # Group records by session, sorted by timestamp
    by_session = {}
    for r in records:
        session = r.get("session", "unknown")
        by_session.setdefault(session, []).append(r)

    longest = {"session": "", "duration_min": 0, "start": "", "end": ""}

    for session, recs in by_session.items():
        recs.sort(key=lambda x: x.get("ts", ""))
        streak_start = None
        streak_count = 0
        for rec in recs:
            status = rec.get("status", "")
            if status in ("idle", "stalled"):
                if streak_start is None:
                    streak_start = rec.get("ts", "")
                streak_count += 1
            else:
                if streak_count > 0:
                    duration = int(streak_count * poll_interval / 60)
                    if duration > longest["duration_min"]:
                        longest = {
                            "session": session,
                            "duration_min": duration,
                            "start": streak_start,
                            "end": rec.get("ts", ""),
                        }
                streak_start = None
                streak_count = 0
        # Handle streak at end of data
        if streak_count > 0:
            duration = int(streak_count * poll_interval / 60)
            if duration > longest["duration_min"]:
                longest = {
                    "session": session,
                    "duration_min": duration,
                    "start": streak_start,
                    "end": recs[-1].get("ts", ""),
                }

    return longest if longest["duration_min"] > 0 else None


def _compute_stall_report(session_records):
    """Compute stall rate from session observations."""
    if not session_records:
        return None
    total = len(session_records)
    stalled = sum(1 for r in session_records if r.get("status") == "stalled")
    rate = (stalled / total * 100) if total > 0 else 0
    return {
        "total_obs": total,
        "stalled_obs": stalled,
        "stall_rate_pct": round(rate, 1),
        "meets_target": rate < TARGET_STALL_RATE_PCT,
    }


def _compute_agent_report(agent_records):
    """Compute agent uptime/throughput from lifecycle events."""
    if not agent_records:
        return None

    started = [r for r in agent_records if r.get("event") == "agent_started"]
    stopped = [r for r in agent_records if r.get("event") == "agent_stopped"]

    # Count by role
    roles = {}
    for r in started:
        role = r.get("role", "unknown")
        roles.setdefault(role, {"launched": 0, "completed": 0, "stalled": 0})
        roles[role]["launched"] += 1

    for r in stopped:
        role = r.get("role", "unknown")
        roles.setdefault(role, {"launched": 0, "completed": 0, "stalled": 0})
        outcome = r.get("outcome", "")
        if outcome == "completed":
            roles[role]["completed"] += 1
        elif outcome in ("dead", "stalled"):
            roles[role]["stalled"] += 1
        else:
            roles[role]["completed"] += 1  # assume completed if not explicitly stalled

    return {
        "total_started": len(started),
        "total_stopped": len(stopped),
        "roles": roles,
    }


def _format_time(ts_str):
    """Extract HH:MM from ISO timestamp."""
    if not ts_str:
        return "?"
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return ts_str[:16] if len(ts_str) >= 16 else ts_str


def generate_report(dates):
    """Generate a markdown metrics report for the given dates."""
    session_records = _load_session_metrics(dates)
    agent_records = _load_agent_metrics(dates)

    if not session_records and not agent_records:
        if len(dates) == 1:
            return f"# Metrics Report — {dates[0]}\n\nNo data available for this date.\n"
        return f"# Metrics Report — {dates[-1]} to {dates[0]}\n\nNo data available for this date range.\n"

    if len(dates) == 1:
        title = f"# Metrics Report — {dates[0]}"
    else:
        title = f"# Metrics Report — {dates[-1]} to {dates[0]}"

    lines = [title, ""]

    # Idle Time
    idle = _compute_idle_report(session_records)
    lines.append("## Idle Time")
    if idle:
        check = "\u2713" if idle["meets_target"] else "\u2717"
        lines.append(f"- Total idle: {idle['total_idle_hours']}h (target: <{TARGET_IDLE_HOURS}h) {check}")
        if idle["longest_stretch"]:
            s = idle["longest_stretch"]
            lines.append(
                f"- Longest idle stretch: {s['duration_min']} min "
                f"({s['session']}, {_format_time(s['start'])}-{_format_time(s['end'])})"
            )
        lines.append(f"- Observations: {idle['active_obs']} active, {idle['idle_obs']} idle, {idle['stalled_obs']} stalled")
    else:
        lines.append("- No session data available")
    lines.append("")

    # Stall Rate
    stall = _compute_stall_report(session_records)
    lines.append("## Stall Rate")
    if stall:
        check = "\u2713" if stall["meets_target"] else "\u2717"
        lines.append(
            f"- Observations: {stall['total_obs']} total, "
            f"{stall['stalled_obs']} stalled ({stall['stall_rate_pct']}%) "
            f"(target: <{TARGET_STALL_RATE_PCT}%) {check}"
        )
    else:
        lines.append("- No session data available")
    lines.append("")

    # Agent Uptime
    agents = _compute_agent_report(agent_records)
    lines.append("## Agent Uptime")
    if agents:
        lines.append(f"- Agents started: {agents['total_started']}")
        lines.append(f"- Agents stopped: {agents['total_stopped']}")
        for role, stats in sorted(agents["roles"].items()):
            lines.append(
                f"- {role.capitalize()}: {stats['launched']} launched, "
                f"{stats['completed']} completed, {stats['stalled']} stalled"
            )
    else:
        lines.append("- No agent lifecycle data available")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="metrics_report",
        description="Generate observability metrics reports from JSONL time-series.",
    )
    parser.add_argument("--date", default=None,
                        help="Date to report on (YYYY-MM-DD or 'today')")
    parser.add_argument("--range", default=None, dest="range_str",
                        help="Date range (e.g. '7d' for last 7 days)")
    parser.add_argument("--output", default=None,
                        help="Write report to file instead of stdout")

    args = parser.parse_args()
    dates = _resolve_dates(args.date, args.range_str)
    report = generate_report(dates)

    if args.output:
        out_path = os.path.join(PROJECT_DIR, args.output) if not os.path.isabs(args.output) else args.output
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(report)
        print(f"Report written to {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
