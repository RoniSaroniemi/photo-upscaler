#!/usr/bin/env python3
"""Generalized tick script — inject a prompt into a tmux session if idle.

Checks whether the target session is at an idle prompt before injecting.
Works for both Claude and Codex agents. Designed to be called from crontab.

Usage:
    python3 tools/codex_tick.py --session <tmux-session> --prompt "<text>" [--tmux-server <server>]

Exit codes:
    0 — prompt sent or skipped (session busy/not-at-prompt)
    1 — error (session not readable, bad arguments)

Stdlib-only. No pip dependencies.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_DIR = os.path.join(PROJECT_DIR, "state")
LOG_FILE = os.path.join(LOG_DIR, "tick.log")

# Indicators that the agent is busy processing
BUSY_PATTERNS = re.compile(
    r"Working \(|Determining|Running|esc to interrupt|Thinking|⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏"
)

# Prompt characters indicating idle state (Claude ❯, Codex ›, generic >)
PROMPT_PATTERN = re.compile(r"^[›❯>]", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tmux_cmd(args: list, server: str | None = None) -> subprocess.CompletedProcess:
    """Run a tmux command, optionally targeting a named server."""
    cmd = ["tmux"]
    if server:
        cmd += ["-L", server]
    cmd += args
    return subprocess.run(cmd, capture_output=True, text=True)


def log(session: str, message: str) -> None:
    """Append a timestamped log line to state/tick.log."""
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{session}] {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass


def capture_pane(session: str, server: str | None = None, lines: int = 20) -> str | None:
    """Capture the last N lines from a tmux pane. Returns None if unreadable."""
    result = tmux_cmd(
        ["capture-pane", "-t", session, "-p", "-S", f"-{lines}"], server
    )
    if result.returncode != 0:
        return None
    return result.stdout


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def should_inject(output: str) -> tuple[bool, str]:
    """Decide whether to inject a prompt based on pane output.

    Returns (should_inject, reason).
    """
    if not output or not output.strip():
        return False, "empty pane output"

    # Check the bottom lines for busy indicators
    bottom = "\n".join(output.strip().split("\n")[-8:])

    if BUSY_PATTERNS.search(bottom):
        return False, "busy"

    if not PROMPT_PATTERN.search(bottom):
        return False, "not at prompt"

    return True, "at prompt"


def inject_prompt(session: str, prompt: str, server: str | None = None) -> bool:
    """Send a prompt into a tmux session. Returns True on success."""
    # Use -l (literal) flag for reliable injection of special characters
    result = tmux_cmd(["send-keys", "-t", session, "-l", prompt], server)
    if result.returncode != 0:
        return False
    # Send Enter to submit
    tmux_cmd(["send-keys", "-t", session, "Enter"], server)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inject a prompt into an idle tmux session (cron tick script).",
    )
    parser.add_argument(
        "--session", required=True,
        help="Target tmux session name",
    )
    parser.add_argument(
        "--prompt", required=True,
        help="Prompt text to inject when session is idle",
    )
    parser.add_argument(
        "--tmux-server", default=None,
        help="tmux -L server name",
    )
    parser.add_argument(
        "--pane-lines", type=int, default=20,
        help="Number of pane lines to capture for state detection (default: 20)",
    )

    args = parser.parse_args()

    # Capture pane output
    output = capture_pane(args.session, args.tmux_server, args.pane_lines)
    if output is None:
        log(args.session, "skip: session not readable")
        return 0  # exit 0 — cron should not retry

    # Decide
    do_inject, reason = should_inject(output)

    if not do_inject:
        log(args.session, f"skip: {reason}")
        return 0

    # Inject
    ok = inject_prompt(args.session, args.prompt, args.tmux_server)
    if ok:
        log(args.session, "sent prompt")
    else:
        log(args.session, "error: send-keys failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
