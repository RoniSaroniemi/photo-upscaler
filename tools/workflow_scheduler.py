#!/usr/bin/env python3
"""Workflow scheduler — manages OS-level cron/launchd schedules for workflows.

Usage:
    python3 tools/workflow_scheduler.py install --workflow-dir .workflows/my-workflow
    python3 tools/workflow_scheduler.py uninstall --workflow-id my-workflow
    python3 tools/workflow_scheduler.py list
    python3 tools/workflow_scheduler.py status --workflow-id my-workflow

Stdlib-only. No pip dependencies.
"""

import argparse
import json
import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLIST_PREFIX = "com.claude-orchestration.workflow"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def emit(msg: str, **kv: object) -> None:
    parts = [msg] + [f"{k}={v}" for k, v in kv.items()]
    print(" | ".join(parts), flush=True)


def is_macos() -> bool:
    return platform.system() == "Darwin"


# ---------------------------------------------------------------------------
# Cron expression parsing
# ---------------------------------------------------------------------------

def parse_cron_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field into a list of integer values.

    Supports: *, N, N-M, N,M, */N, N-M/S
    """
    values = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            range_part, step = part.split("/", 1)
            step = int(step)
            if range_part == "*":
                start, end = min_val, max_val
            elif "-" in range_part:
                start, end = map(int, range_part.split("-", 1))
            else:
                start, end = int(range_part), max_val
            values.update(range(start, end + 1, step))
        elif "-" in part:
            start, end = map(int, part.split("-", 1))
            values.update(range(start, end + 1))
        else:
            values.add(int(part))
    return sorted(values)


def cron_to_calendar_intervals(cron_expr: str) -> list[dict]:
    """Convert a 5-field cron expression to launchd StartCalendarInterval dicts.

    Fields: minute hour day-of-month month day-of-week
    Day-of-week: 0=Sunday, 1=Monday, ..., 6=Saturday (or 7=Sunday)
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Expected 5-field cron expression, got: {cron_expr}")

    minutes = parse_cron_field(fields[0], 0, 59)
    hours = parse_cron_field(fields[1], 0, 23)
    days_of_month = parse_cron_field(fields[2], 1, 31) if fields[2] != "*" else None
    months = parse_cron_field(fields[3], 1, 12) if fields[3] != "*" else None
    days_of_week = parse_cron_field(fields[4], 0, 7) if fields[4] != "*" else None

    # Normalize day-of-week: 7 -> 0 (Sunday)
    if days_of_week:
        days_of_week = sorted(set(0 if d == 7 else d for d in days_of_week))

    intervals = []
    for minute in minutes:
        for hour in hours:
            base = {"Minute": minute, "Hour": hour}

            if days_of_week and days_of_month:
                # Both specified: create entries for both (OR semantics in cron)
                for dow in days_of_week:
                    entry = {**base, "Weekday": dow}
                    if months:
                        for month in months:
                            intervals.append({**entry, "Month": month})
                    else:
                        intervals.append(entry)
                for dom in days_of_month:
                    entry = {**base, "Day": dom}
                    if months:
                        for month in months:
                            intervals.append({**entry, "Month": month})
                    else:
                        intervals.append(entry)
            elif days_of_week:
                for dow in days_of_week:
                    entry = {**base, "Weekday": dow}
                    if months:
                        for month in months:
                            intervals.append({**entry, "Month": month})
                    else:
                        intervals.append(entry)
            elif days_of_month:
                for dom in days_of_month:
                    entry = {**base, "Day": dom}
                    if months:
                        for month in months:
                            intervals.append({**entry, "Month": month})
                    else:
                        intervals.append(entry)
            else:
                if months:
                    for month in months:
                        intervals.append({**base, "Month": month})
                else:
                    intervals.append(base)

    return intervals


# ---------------------------------------------------------------------------
# launchd management
# ---------------------------------------------------------------------------

def plist_label(workflow_id: str) -> str:
    return f"{PLIST_PREFIX}.{workflow_id}"


def plist_path(workflow_id: str) -> Path:
    return LAUNCH_AGENTS_DIR / f"{plist_label(workflow_id)}.plist"


def generate_plist(workflow_dir: Path, config: dict) -> dict:
    """Generate a launchd plist dict from workflow config."""
    workflow_id = config["id"]
    schedule = config.get("schedule", {})
    cron_expr = schedule.get("cron", "0 9 * * *")

    run_script = (workflow_dir / "run.sh").resolve()
    artifacts_dir = workflow_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Common bin paths
    path_dirs = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
        "/usr/bin",
        "/bin",
    ]

    plist = {
        "Label": plist_label(workflow_id),
        "ProgramArguments": ["/bin/bash", str(run_script)],
        "StartCalendarInterval": cron_to_calendar_intervals(cron_expr),
        "StandardOutPath": str(artifacts_dir / "launchd-stdout.log"),
        "StandardErrorPath": str(artifacts_dir / "launchd-stderr.log"),
        "WorkingDirectory": str(workflow_dir.parent.parent.resolve()),
        "EnvironmentVariables": {
            "PATH": ":".join(path_dirs),
        },
    }
    return plist


def install_launchd(workflow_dir: Path, config: dict) -> str:
    """Install a launchd plist for a workflow. Returns the plist path."""
    workflow_id = config["id"]
    label = plist_label(workflow_id)
    path = plist_path(workflow_id)

    # Unload existing if present
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)],
                        capture_output=True)

    # Generate and write plist
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    plist_data = generate_plist(workflow_dir, config)

    with open(path, "wb") as f:
        plistlib.dump(plist_data, f)

    # Make run.sh executable
    run_sh = workflow_dir / "run.sh"
    if run_sh.exists():
        run_sh.chmod(0o755)

    # Load the plist
    result = subprocess.run(["launchctl", "load", str(path)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        emit("launchctl_load_failed", error=result.stderr.strip())
    else:
        emit("launchd_installed", label=label, plist=str(path))

    return str(path)


def uninstall_launchd(workflow_id: str) -> bool:
    """Uninstall a launchd plist. Returns True if removed."""
    path = plist_path(workflow_id)
    if not path.exists():
        emit("plist_not_found", workflow_id=workflow_id)
        return False

    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    path.unlink()
    emit("launchd_uninstalled", workflow_id=workflow_id)
    return True


def list_launchd() -> list[dict]:
    """List installed workflow plists."""
    entries = []
    if not LAUNCH_AGENTS_DIR.exists():
        return entries

    for p in LAUNCH_AGENTS_DIR.glob(f"{PLIST_PREFIX}.*.plist"):
        try:
            with open(p, "rb") as f:
                data = plistlib.load(f)
            label = data.get("Label", "")
            workflow_id = label.replace(f"{PLIST_PREFIX}.", "")
            intervals = data.get("StartCalendarInterval", [])
            entries.append({
                "workflow_id": workflow_id,
                "label": label,
                "plist_path": str(p),
                "intervals_count": len(intervals) if isinstance(intervals, list) else 1,
                "working_dir": data.get("WorkingDirectory", ""),
            })
        except Exception as exc:
            entries.append({
                "workflow_id": p.stem.replace(f"{PLIST_PREFIX}.", ""),
                "error": str(exc),
            })
    return entries


def status_launchd(workflow_id: str) -> dict:
    """Check the status of a workflow's launchd job."""
    path = plist_path(workflow_id)
    label = plist_label(workflow_id)

    result = {"workflow_id": workflow_id, "installed": path.exists()}
    if not path.exists():
        return result

    # Check if loaded
    list_result = subprocess.run(
        ["launchctl", "list", label],
        capture_output=True, text=True,
    )
    result["loaded"] = list_result.returncode == 0
    if list_result.returncode == 0:
        # Parse PID and last exit status from output
        for line in list_result.stdout.strip().split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                result["pid"] = parts[0] if parts[0] != "-" else None
                result["last_exit_status"] = int(parts[1]) if parts[1] != "-" else None

    # Read plist for schedule info
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        intervals = data.get("StartCalendarInterval", [])
        result["intervals_count"] = len(intervals) if isinstance(intervals, list) else 1
        result["working_dir"] = data.get("WorkingDirectory", "")
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Crontab management (non-macOS fallback)
# ---------------------------------------------------------------------------

CRONTAB_MARKER = "# claude-orchestration-workflow:"


def install_crontab(workflow_dir: Path, config: dict) -> str:
    """Install a crontab entry for a workflow."""
    workflow_id = config["id"]
    schedule = config.get("schedule", {})
    cron_expr = schedule.get("cron", "0 9 * * *")
    run_script = (workflow_dir / "run.sh").resolve()

    # Make executable
    if run_script.exists():
        run_script.chmod(0o755)

    marker = f"{CRONTAB_MARKER}{workflow_id}"
    new_line = f"{cron_expr} {run_script} {marker}"

    # Get current crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = result.stdout if result.returncode == 0 else ""

    # Remove existing entry for this workflow
    lines = [l for l in current.split("\n")
             if marker not in l and l.strip()]
    lines.append(new_line)

    # Install
    proc = subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        emit("crontab_install_failed", error=proc.stderr.strip())
    else:
        emit("crontab_installed", workflow_id=workflow_id)
    return new_line


def uninstall_crontab(workflow_id: str) -> bool:
    """Remove a workflow's crontab entry."""
    marker = f"{CRONTAB_MARKER}{workflow_id}"
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return False

    lines = [l for l in result.stdout.split("\n") if marker not in l and l.strip()]
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                    capture_output=True, text=True)
    emit("crontab_uninstalled", workflow_id=workflow_id)
    return True


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    workflow_dir = Path(args.workflow_dir).resolve()
    config_path = workflow_dir / "workflow.json"
    if not config_path.exists():
        emit("error", msg=f"workflow.json not found in {workflow_dir}")
        return 1

    config = load_json(config_path)
    if is_macos():
        path = install_launchd(workflow_dir, config)
    else:
        path = install_crontab(workflow_dir, config)

    # Update registry
    registry_path = workflow_dir.parent / "registry.json"
    if registry_path.exists():
        registry = load_json(registry_path)
        workflows = registry.get("workflows", [])
        entry = None
        for w in workflows:
            if w.get("id") == config["id"]:
                entry = w
                break
        if entry is None:
            entry = {"id": config["id"]}
            workflows.append(entry)
        entry["enabled"] = True
        entry["schedule"] = config.get("schedule", {}).get("cron", "")
        entry["timezone"] = config.get("schedule", {}).get("timezone", "")
        entry["scheduler"] = "launchd" if is_macos() else "crontab"
        entry["scheduler_id"] = plist_label(config["id"]) if is_macos() else f"crontab:{config['id']}"
        registry["workflows"] = workflows
        save_json(registry_path, registry)

    if args.json_output:
        print(json.dumps({"status": "installed", "path": path}))
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    if is_macos():
        removed = uninstall_launchd(args.workflow_id)
    else:
        removed = uninstall_crontab(args.workflow_id)

    if args.json_output:
        print(json.dumps({"status": "uninstalled" if removed else "not_found"}))
    return 0 if removed else 1


def cmd_list(args: argparse.Namespace) -> int:
    if is_macos():
        entries = list_launchd()
    else:
        # Read from registry
        entries = []

    if args.json_output:
        print(json.dumps(entries, indent=2))
    else:
        if not entries:
            print("No workflow schedules installed.")
        else:
            for e in entries:
                wid = e.get("workflow_id", "?")
                label = e.get("label", "?")
                intervals = e.get("intervals_count", "?")
                print(f"  {wid} | label={label} | intervals={intervals}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    if is_macos():
        info = status_launchd(args.workflow_id)
    else:
        info = {"workflow_id": args.workflow_id, "scheduler": "crontab"}

    if args.json_output:
        print(json.dumps(info, indent=2))
    else:
        for k, v in info.items():
            print(f"  {k}: {v}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage OS-level scheduling for workflows")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output as JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Install a workflow schedule")
    p_install.add_argument("--workflow-dir", required=True,
                           help="Path to the workflow directory")

    p_uninstall = sub.add_parser("uninstall", help="Uninstall a workflow schedule")
    p_uninstall.add_argument("--workflow-id", required=True,
                             help="Workflow ID to uninstall")

    sub.add_parser("list", help="List installed workflow schedules")

    p_status = sub.add_parser("status", help="Check workflow schedule status")
    p_status.add_argument("--workflow-id", required=True,
                          help="Workflow ID to check")

    args = parser.parse_args()

    commands = {
        "install": cmd_install,
        "uninstall": cmd_uninstall,
        "list": cmd_list,
        "status": cmd_status,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
