#!/usr/bin/env python3
"""Observation registry — tracks observer reports and their review status.

Usage:
    python3 tools/observer_registry.py init
    python3 tools/observer_registry.py list [--status STATUS] [--json]
    python3 tools/observer_registry.py show <obs-id>
    python3 tools/observer_registry.py add '<json>'
    python3 tools/observer_registry.py mark-processed <obs-id>
"""
import argparse
import json
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(PROJECT_DIR, ".cpo", "observations", "registry.json")

VALID_STATUSES = ("pending", "processed")

REQUIRED_ENTRY_FIELDS = ("id", "run_id", "target_session", "report_path", "status", "created")


def _load_registry() -> dict:
    """Load registry from disk, returning empty structure if missing."""
    try:
        with open(REGISTRY_PATH) as f:
            data = json.load(f)
        if "entries" not in data:
            data["entries"] = []
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "entries": []}


def _save_registry(data: dict) -> None:
    """Atomically write registry (tempfile + os.replace)."""
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(REGISTRY_PATH), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, REGISTRY_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find_entry(entries: list, obs_id: str):
    """Return (index, entry_dict) or (None, None)."""
    for i, e in enumerate(entries):
        if e.get("id") == obs_id:
            return i, e
    return None, None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args) -> int:
    """Create empty registry if not present."""
    if os.path.exists(REGISTRY_PATH):
        print(f"Registry already exists at {REGISTRY_PATH}")
        return 0
    _save_registry({"version": 1, "entries": []})
    print(f"Initialized empty registry at {REGISTRY_PATH}")
    return 0


def cmd_list(args) -> int:
    """List entries, optionally filtered by status."""
    data = _load_registry()
    entries = data["entries"]
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]

    if args.json:
        print(json.dumps(entries, indent=2))
        return 0

    if not entries:
        if args.status:
            print(f"No observations with status '{args.status}'.")
        else:
            print("No observations recorded yet.")
        return 0

    # Group by status
    by_status = {}
    for e in entries:
        s = e.get("status", "unknown")
        by_status.setdefault(s, []).append(e)

    for status, group in sorted(by_status.items()):
        print(f"\n== {status.upper()} ({len(group)}) ==")
        for e in group:
            print(f"  {e['id']}  run={e.get('run_id', '?')}  target={e.get('target_session', '?')}  created={e.get('created', '?')}")

    print(f"\nTotal: {len(entries)} observation(s)")
    return 0


def cmd_show(args) -> int:
    """Print the report content for an observation."""
    data = _load_registry()
    _, entry = _find_entry(data["entries"], args.obs_id)
    if entry is None:
        print(f"Observation '{args.obs_id}' not found.", file=sys.stderr)
        return 1

    report_path = entry.get("report_path", "")
    # Resolve relative to project root
    if not os.path.isabs(report_path):
        report_path = os.path.join(PROJECT_DIR, report_path)

    if not os.path.exists(report_path):
        print(f"Report file not found: {report_path}", file=sys.stderr)
        print(f"Registry entry: {json.dumps(entry, indent=2)}")
        return 1

    with open(report_path) as f:
        print(f.read())
    return 0


def cmd_add(args) -> int:
    """Append an entry to the registry."""
    try:
        entry = json.loads(args.entry_json)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1

    # Validate required fields
    missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in entry]
    if missing:
        print(f"Missing required fields: {', '.join(missing)}", file=sys.stderr)
        return 1

    if entry.get("status") and entry["status"] not in VALID_STATUSES:
        print(f"Invalid status '{entry['status']}'. Valid: {', '.join(VALID_STATUSES)}", file=sys.stderr)
        return 1

    data = _load_registry()

    # Check for duplicate ID
    _, existing = _find_entry(data["entries"], entry["id"])
    if existing:
        print(f"Entry '{entry['id']}' already exists. Use mark-processed to update status.", file=sys.stderr)
        return 1

    data["entries"].append(entry)
    _save_registry(data)
    print(f"Added observation '{entry['id']}'")
    return 0


def cmd_mark_processed(args) -> int:
    """Set an observation's status to 'processed'."""
    data = _load_registry()
    idx, entry = _find_entry(data["entries"], args.obs_id)
    if entry is None:
        print(f"Observation '{args.obs_id}' not found.", file=sys.stderr)
        return 1

    old_status = entry.get("status")
    if old_status == "processed":
        print(f"Observation '{args.obs_id}' is already processed.")
        return 0

    entry["status"] = "processed"
    _save_registry(data)
    print(f"Marked '{args.obs_id}' as processed (was: {old_status})")
    return 0


# ---------------------------------------------------------------------------
# Public API for programmatic use
# ---------------------------------------------------------------------------

def add_entry(entry: dict) -> None:
    """Add an observation entry programmatically."""
    data = _load_registry()
    _, existing = _find_entry(data["entries"], entry["id"])
    if existing:
        raise ValueError(f"Entry '{entry['id']}' already exists")
    data["entries"].append(entry)
    _save_registry(data)


def mark_processed(obs_id: str) -> None:
    """Mark an observation as processed programmatically."""
    data = _load_registry()
    _, entry = _find_entry(data["entries"], obs_id)
    if entry is None:
        raise ValueError(f"Observation '{obs_id}' not found")
    entry["status"] = "processed"
    _save_registry(data)


def list_entries(status: str = None) -> list:
    """Return observation entries, optionally filtered by status."""
    data = _load_registry()
    entries = data["entries"]
    if status:
        entries = [e for e in entries if e.get("status") == status]
    return entries


def load_registry() -> dict:
    """Load and return the registry (read-only access)."""
    return _load_registry()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="observer_registry",
        description="Manage the observation registry for meta-learner observer reports.",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="Create empty registry if not present")

    # list
    p = sub.add_parser("list", help="List observation entries")
    p.add_argument("--status", choices=VALID_STATUSES, help="Filter by status")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # show
    p = sub.add_parser("show", help="Print report content for an observation")
    p.add_argument("obs_id", help="Observation ID (e.g., obs-20260328-160000)")

    # add
    p = sub.add_parser("add", help="Append an entry to the registry")
    p.add_argument("entry_json", help="JSON string with entry data")

    # mark-processed
    p = sub.add_parser("mark-processed", help="Set observation status to processed")
    p.add_argument("obs_id", help="Observation ID to mark as processed")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "init": cmd_init,
        "list": cmd_list,
        "show": cmd_show,
        "add": cmd_add,
        "mark-processed": cmd_mark_processed,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
