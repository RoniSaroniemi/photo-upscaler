#!/usr/bin/env python3
"""Backlog integrator — merges agent findings files into backlog.json.

Agents write findings to .cpo/findings/ instead of modifying backlog.json
directly. This tool reads unprocessed findings, assigns sequential IDs,
appends them to backlog.json, and marks findings as processed.

Usage:
    python3 tools/backlog_integrator.py [--dry-run] [--findings-dir PATH] [--backlog PATH]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def get_main_repo_path() -> str:
    """Derive the main repo path from git worktree list.

    Works from any worktree — the first entry is always the main working tree.
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git worktree list failed: {result.stderr.strip()}")

    first_line = result.stdout.split("\n")[0]
    if not first_line.startswith("worktree "):
        raise RuntimeError(f"Unexpected git worktree output: {first_line}")

    return first_line.replace("worktree ", "", 1)


def load_findings(findings_dir: str) -> list[tuple[str, dict]]:
    """Read all unprocessed findings files from the findings directory.

    Returns list of (filepath, parsed_json) tuples, sorted by written_at.
    Skips files that are already processed or malformed.
    """
    findings = []
    findings_path = Path(findings_dir)

    if not findings_path.is_dir():
        return findings

    for fpath in sorted(findings_path.glob("*.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  SKIP {fpath.name}: parse error — {e}", file=sys.stderr)
            continue

        if data.get("processed", False):
            continue

        if data.get("schema_version") != 1:
            print(
                f"  SKIP {fpath.name}: unsupported schema_version "
                f"{data.get('schema_version')}",
                file=sys.stderr,
            )
            continue

        if not data.get("items"):
            print(f"  SKIP {fpath.name}: no items", file=sys.stderr)
            continue

        findings.append((str(fpath), data))

    # Sort by written_at for deterministic ordering
    findings.sort(key=lambda x: x[1].get("written_at", ""))
    return findings


def integrate(backlog_path: str, findings_dir: str, dry_run: bool = False) -> int:
    """Integrate unprocessed findings into backlog.json.

    Returns the number of items integrated.
    """
    # Load backlog
    with open(backlog_path) as f:
        backlog = json.load(f)

    next_id = backlog.get("next_id", 1)
    entries = backlog.get("entries", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # Load unprocessed findings
    findings = load_findings(findings_dir)

    if not findings:
        print("No unprocessed findings files found.")
        return 0

    total_items = 0

    for fpath, data in findings:
        fname = Path(fpath).name
        source = data.get("source", "unknown")
        source_ref = data.get("source_ref", "")
        items = data.get("items", [])

        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {fname} "
              f"({len(items)} items from {source}):")

        for item in items:
            item_id = f"BL-{next_id:03d}"
            entry = {
                "id": item_id,
                "title": item["title"],
                "status": "proposed",
                "priority": item.get("priority", "P2"),
                "source": source,
                "source_ref": source_ref,
                "category": item.get("category", "uncategorized"),
                "created": today,
                "updated": today,
                "notes": item.get("notes", ""),
            }

            print(f"  {item_id}: {item['title']} [{entry['priority']}]")

            if not dry_run:
                entries.append(entry)

            next_id += 1
            total_items += 1

        # Mark findings file as processed
        if not dry_run:
            data["processed"] = True
            data["processed_at"] = now_iso
            with open(fpath, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")

    # Write updated backlog
    if not dry_run and total_items > 0:
        backlog["next_id"] = next_id
        backlog["entries"] = entries

        # Atomic write: write to temp file, then rename
        backlog_dir = os.path.dirname(os.path.abspath(backlog_path))
        fd, tmp_path = tempfile.mkstemp(dir=backlog_dir, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(backlog, f, indent=2)
                f.write("\n")
            os.replace(tmp_path, backlog_path)
        except Exception:
            os.unlink(tmp_path)
            raise

    action = "Would integrate" if dry_run else "Integrated"
    print(f"\n{action} {total_items} items from {len(findings)} findings file(s).")
    if not dry_run and total_items > 0:
        print(f"next_id is now {next_id}.")

    return total_items


def main():
    parser = argparse.ArgumentParser(
        description="Integrate agent findings into backlog.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be integrated without writing anything",
    )
    parser.add_argument(
        "--findings-dir",
        default=None,
        help="Path to findings directory (default: <main-repo>/.cpo/findings)",
    )
    parser.add_argument(
        "--backlog",
        default=None,
        help="Path to backlog.json (default: <main-repo>/.cpo/backlog.json)",
    )

    args = parser.parse_args()

    # Resolve paths
    if args.findings_dir and args.backlog:
        findings_dir = args.findings_dir
        backlog_path = args.backlog
    else:
        try:
            main_repo = get_main_repo_path()
        except RuntimeError as e:
            print(f"Error resolving main repo path: {e}", file=sys.stderr)
            sys.exit(1)

        findings_dir = args.findings_dir or os.path.join(
            main_repo, ".cpo", "findings"
        )
        backlog_path = args.backlog or os.path.join(
            main_repo, ".cpo", "backlog.json"
        )

    if not os.path.isfile(backlog_path):
        print(f"Error: backlog not found at {backlog_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(findings_dir):
        print(f"Error: findings directory not found at {findings_dir}", file=sys.stderr)
        sys.exit(1)

    count = integrate(backlog_path, findings_dir, dry_run=args.dry_run)
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
