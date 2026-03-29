#!/usr/bin/env python3
"""Codex /loop — manage recurring prompt injection via crontab.

Usage:
    python3 tools/codex_loop.py start 30m "Check status and report"
    python3 tools/codex_loop.py start 2h "Run full test suite"
    python3 tools/codex_loop.py list
    python3 tools/codex_loop.py stop                  # stop loop for current session
    python3 tools/codex_loop.py stop <session-name>   # stop loop for named session

Interval formats:
    Ns  — seconds (rounded up to 1m minimum for cron)
    Nm  — every N minutes
    Nh  — every N hours

Installs crontab entries that call codex_tick.py to inject prompts into
idle tmux sessions.  Each entry is tagged with a marker comment for safe
management:  # codex-loop:<session-name>

Stdlib-only. No pip dependencies.
"""

import argparse
import os
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TICK_SCRIPT = os.path.join(SCRIPT_DIR, "codex_tick.py")

CRONTAB_MARKER_PREFIX = "# codex-loop:"

INTERVAL_RE = re.compile(r"^(\d+)\s*([smh])$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Interval parsing
# ---------------------------------------------------------------------------

def parse_interval(spec: str) -> str:
    """Convert a human interval spec (30s, 5m, 2h) to a 5-field cron expression.

    Rules:
        Ns  → round up to 1 minute minimum  →  */1 * * * *
        Nm  → */N * * * *
        Nh  → 0 */N * * *
    """
    m = INTERVAL_RE.match(spec.strip())
    if not m:
        raise ValueError(
            f"Invalid interval '{spec}'. Use <number><s|m|h>, e.g. 30s, 5m, 2h"
        )

    value = int(m.group(1))
    unit = m.group(2).lower()

    if value <= 0:
        raise ValueError("Interval must be a positive number")

    if unit == "s":
        # Cron minimum is 1 minute; round up
        minutes = max(1, (value + 59) // 60)
        return f"*/{minutes} * * * *"
    elif unit == "m":
        minutes = max(1, value)
        if minutes >= 60:
            # Convert to hourly
            hours = minutes // 60
            return f"0 */{hours} * * *"
        return f"*/{minutes} * * * *"
    elif unit == "h":
        hours = max(1, value)
        return f"0 */{hours} * * *"
    else:
        raise ValueError(f"Unknown unit '{unit}'")


# ---------------------------------------------------------------------------
# tmux session detection
# ---------------------------------------------------------------------------

def get_current_tmux_session() -> str | None:
    """Return the current tmux session name, or None if not in tmux."""
    # TMUX env var is set inside tmux: /tmp/tmux-501/default,12345,0
    if not os.environ.get("TMUX"):
        return None
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#S"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# Crontab helpers
# ---------------------------------------------------------------------------

def _read_crontab() -> str:
    """Read the current user crontab. Returns empty string if none."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def _write_crontab(content: str) -> bool:
    """Write a new crontab. Returns True on success."""
    result = subprocess.run(
        ["crontab", "-"],
        input=content,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Error writing crontab: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def _marker(session: str) -> str:
    return f"{CRONTAB_MARKER_PREFIX}{session}"


def _find_loops(crontab: str, session: str | None = None) -> list[dict]:
    """Parse crontab lines matching our marker.  If session is given, filter."""
    loops = []
    for line in crontab.split("\n"):
        if CRONTAB_MARKER_PREFIX not in line:
            continue
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Extract session from marker
        marker_idx = line.index(CRONTAB_MARKER_PREFIX)
        sess = line[marker_idx + len(CRONTAB_MARKER_PREFIX):].strip()
        if session and sess != session:
            continue
        # Extract cron expression (first 5 fields)
        parts = line[:marker_idx].strip().split()
        if len(parts) >= 5:
            cron_expr = " ".join(parts[:5])
            command = " ".join(parts[5:])
        else:
            cron_expr = "?"
            command = line[:marker_idx].strip()
        # Extract prompt from --prompt argument
        prompt_match = re.search(r'--prompt\s+"([^"]*)"', command)
        prompt = prompt_match.group(1) if prompt_match else "?"
        loops.append({
            "session": sess,
            "cron": cron_expr,
            "prompt": prompt,
            "line": line,
        })
    return loops


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_start(session: str, interval_spec: str, prompt: str,
              tmux_server: str | None = None) -> int:
    """Install a crontab entry for recurring prompt injection."""
    # Resolve absolute path to tick script
    if not os.path.isfile(TICK_SCRIPT):
        print(f"Error: tick script not found at {TICK_SCRIPT}", file=sys.stderr)
        return 1

    tick_path = os.path.abspath(TICK_SCRIPT)
    python = sys.executable or "python3"

    # Parse interval
    try:
        cron_expr = parse_interval(interval_spec)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Build the crontab command
    cmd_parts = [python, tick_path, "--session", session, "--prompt", f'"{prompt}"']
    if tmux_server:
        cmd_parts += ["--tmux-server", tmux_server]
    command_str = " ".join(cmd_parts)

    marker = _marker(session)
    new_line = f"{cron_expr} {command_str} {marker}"

    # Read current crontab, remove any existing loop for this session
    current = _read_crontab()
    lines = [l for l in current.split("\n") if l.strip() and marker not in l]
    lines.append(new_line)

    if not _write_crontab("\n".join(lines) + "\n"):
        return 1

    print(f"Loop started: '{prompt}' every {interval_spec} (cron: {cron_expr})")
    print(f"  Session: {session}")
    print(f"  Job ID:  codex-loop-{session}")
    return 0


def cmd_list(session: str | None = None) -> int:
    """List active loops, optionally filtered to a session."""
    current = _read_crontab()
    loops = _find_loops(current, session)

    if not loops:
        scope = f" for session '{session}'" if session else ""
        print(f"No active loops{scope}.")
        return 0

    print(f"Active loops ({len(loops)}):")
    for loop in loops:
        print(f"  [{loop['session']}] {loop['cron']}  \"{loop['prompt']}\"")
    return 0


def cmd_stop(session: str | None = None) -> int:
    """Remove crontab entries for a session (or all loops if no session)."""
    current = _read_crontab()

    if session:
        marker = _marker(session)
        lines = [l for l in current.split("\n") if marker not in l]
        removed = [l for l in current.split("\n") if marker in l and l.strip()]
    else:
        # Remove ALL codex-loop entries
        lines = [l for l in current.split("\n") if CRONTAB_MARKER_PREFIX not in l]
        removed = [l for l in current.split("\n")
                    if CRONTAB_MARKER_PREFIX in l and l.strip()]

    if not removed:
        scope = f" for session '{session}'" if session else ""
        print(f"No active loops{scope} to stop.")
        return 0

    # Keep non-empty lines
    lines = [l for l in lines if l.strip()]
    content = "\n".join(lines) + "\n" if lines else ""

    if not _write_crontab(content):
        return 1

    print(f"Stopped {len(removed)} loop(s):")
    for line in removed:
        # Extract session from marker
        idx = line.index(CRONTAB_MARKER_PREFIX)
        sess = line[idx + len(CRONTAB_MARKER_PREFIX):].strip()
        print(f"  Removed: codex-loop-{sess}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage recurring prompt injection loops for Codex sessions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start 5m "Check build status"
  %(prog)s start 2h "Run full test suite" --session my-session
  %(prog)s list
  %(prog)s stop
  %(prog)s stop --session my-session
""",
    )

    sub = parser.add_subparsers(dest="command")

    # --- start ---
    p_start = sub.add_parser("start", help="Start a recurring loop")
    p_start.add_argument("interval",
                         help="Interval: <N>s, <N>m, or <N>h (e.g. 5m, 2h)")
    p_start.add_argument("prompt", help="Prompt text to inject each tick")
    p_start.add_argument("--session", default=None,
                         help="tmux session name (auto-detected if omitted)")
    p_start.add_argument("--tmux-server", default=None,
                         help="tmux -L server name")

    # --- list ---
    p_list = sub.add_parser("list", help="List active loops")
    p_list.add_argument("--session", default=None,
                        help="Filter to a specific session")

    # --- stop ---
    p_stop = sub.add_parser("stop", help="Stop loops")
    p_stop.add_argument("--session", default=None,
                        help="Session to stop (all if omitted)")

    args = parser.parse_args()

    if not args.command:
        # No subcommand → default to list
        return cmd_list()

    if args.command == "start":
        session = args.session or get_current_tmux_session()
        if not session:
            print(
                "Error: Could not detect tmux session. "
                "Use --session <name> to specify.",
                file=sys.stderr,
            )
            return 1
        return cmd_start(session, args.interval, args.prompt, args.tmux_server)

    elif args.command == "list":
        return cmd_list(args.session)

    elif args.command == "stop":
        return cmd_stop(args.session)

    return 0


if __name__ == "__main__":
    sys.exit(main())
