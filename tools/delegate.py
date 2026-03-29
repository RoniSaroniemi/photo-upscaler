#!/usr/bin/env python3
"""Backward-compatible wrapper — delegates to tools/launch.py --role pair.

Original delegate.py functionality now lives in launch.py. This wrapper
preserves the existing CLI interface so nothing breaks for scripts or
agents that still reference delegate.py.

Usage (unchanged):
    python3 tools/delegate.py --brief .cpo/briefs/my-task.md --branch feature/my-task
    python3 tools/delegate.py --brief x.md --branch y --provider codex --json
    python3 tools/delegate.py --brief x.md --branch y --dry-run

Stdlib-only. No pip dependencies.
"""

import os
import subprocess
import sys


def main():
    """Forward all arguments to launch.py --role pair."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    launch_py = os.path.join(script_dir, "launch.py")

    cmd = [sys.executable, launch_py, "--role", "pair"] + sys.argv[1:]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
