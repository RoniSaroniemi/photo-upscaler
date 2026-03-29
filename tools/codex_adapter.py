#!/usr/bin/env python3
"""Codex adapter CLI — check provider availability and get launch commands."""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Optional


def provider_available(provider: str) -> dict:
    """Check if a provider CLI is available and return its info."""
    path = shutil.which(provider)
    if not path:
        return {"available": False, "version": None, "model": None}

    version = None
    try:
        result = subprocess.run(
            [provider, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    model_map = {
        "codex": "codex",
        "claude": "claude",
    }

    return {
        "available": True,
        "version": version,
        "model": model_map.get(provider, provider),
    }


def get_launch_command(provider: str, mode: str) -> str:
    """Return the launch command string for a provider/mode combination."""
    commands = {
        ("codex", "exec"): "codex exec --dangerously-bypass-approvals-and-sandbox",
        ("codex", "interactive"): "codex --dangerously-bypass-approvals-and-sandbox",
        ("claude", "exec"): "claude -p --dangerously-skip-permissions",
        ("claude", "interactive"): "claude --dangerously-skip-permissions",
    }
    key = (provider, mode)
    if key not in commands:
        raise ValueError(f"Unknown provider/mode: {provider}/{mode}")
    return commands[key]


def parse_tokens_used(output: str) -> Optional[int]:
    """Try to extract token count from provider output text."""
    # Match patterns like "tokens: 1234", "token_count: 1234", "1234 tokens"
    patterns = [
        r"tokens?\s*[:=]\s*(\d+)",
        r"(\d+)\s+tokens?\b",
        r"token_count\s*[:=]\s*(\d+)",
        r"total_tokens\s*[:=]\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def log_usage(session: str, tokens: Optional[int], model: str) -> None:
    """Atomic append of a JSON line to state/codex-usage.jsonl."""
    state_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state")
    os.makedirs(state_dir, exist_ok=True)
    usage_path = os.path.join(state_dir, "codex-usage.jsonl")

    entry = json.dumps({
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session": session,
        "tokens": tokens,
        "model": model,
    })

    # Atomic write: write to .tmp then rename to append
    fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
    try:
        # Read existing content if file exists
        existing = ""
        if os.path.exists(usage_path):
            with open(usage_path, "r") as f:
                existing = f.read()
        with os.fdopen(fd, "w") as tmp_f:
            if existing:
                tmp_f.write(existing)
            tmp_f.write(entry + "\n")
        os.rename(tmp_path, usage_path)
    except Exception:
        # Clean up tmp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def run_exec(provider: str, prompt: str, workdir: str, model: Optional[str],
             timeout: int) -> dict:
    """Run a provider exec command and return structured result."""
    if provider == "codex":
        cmd = ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
    elif provider == "claude":
        cmd = ["claude", "-p", "--dangerously-skip-permissions"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
        combined = result.stdout + result.stderr
        tokens = parse_tokens_used(combined)
        return {
            "exit_code": result.returncode,
            "output_text": result.stdout.strip(),
            "tokens_used": tokens,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "output_text": f"Timed out after {timeout}s",
            "tokens_used": None,
        }


def cmd_exec(args):
    provider = args.provider
    result = run_exec(provider, args.prompt, args.workdir, args.model, args.timeout)

    session_id = uuid.uuid4().hex[:12]
    model_name = args.model or provider
    log_usage(session_id, result["tokens_used"], model_name)

    print(json.dumps(result, indent=2))
    sys.exit(0 if result["exit_code"] == 0 else 1)


def launch_session(session: str, workdir: str) -> dict:
    """Create a tmux session running codex --dangerously-bypass-approvals-and-sandbox."""
    # Create detached tmux session
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-c", workdir],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}

    # Send the launch command into the session
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "codex --dangerously-bypass-approvals-and-sandbox", "Enter"],
        capture_output=True, text=True,
    )

    # Wait briefly for init
    time.sleep(3)

    return {"ok": True, "session": session}


def inject_prompt(session: str, prompt: str) -> dict:
    """Send a prompt into an existing tmux session."""
    # Send the prompt text
    result = subprocess.run(
        ["tmux", "send-keys", "-t", session, prompt, "Enter"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}

    # Brief pause then extra Enter for safety
    time.sleep(2)
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "Enter"],
        capture_output=True, text=True,
    )

    return {"ok": True, "session": session}


def session_status(session: str) -> dict:
    """Check if a tmux session is alive, idle, and grab recent output."""
    # Check alive
    alive_result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        capture_output=True, text=True,
    )
    alive = alive_result.returncode == 0

    if not alive:
        return {"alive": False, "idle": False, "last_output": ""}

    # Capture recent pane output (last 5 lines)
    capture_result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p", "-S", "-5"],
        capture_output=True, text=True,
    )
    last_output = capture_result.stdout.rstrip()

    # Check for idle prompt character (U+203A right single angle quotation mark)
    idle = "\u203a" in last_output

    return {"alive": True, "idle": idle, "last_output": last_output}


def cmd_launch(args):
    result = launch_session(args.session, args.workdir)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


def cmd_inject(args):
    result = inject_prompt(args.session, args.prompt)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


def cmd_status(args):
    result = session_status(args.session)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["alive"] else 1)


def cmd_check(args):
    info = provider_available(args.provider)
    print(json.dumps(info, indent=2))
    sys.exit(0 if info["available"] else 1)


def cmd_command(args):
    try:
        command = get_launch_command(args.provider, args.mode)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"command": command}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Codex adapter CLI")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    check_p = sub.add_parser("check", help="Check provider availability")
    check_p.add_argument(
        "--provider", required=True, choices=["codex", "claude"],
        help="Provider to check",
    )
    check_p.set_defaults(func=cmd_check)

    exec_p = sub.add_parser("exec", help="Execute a prompt via provider")
    exec_p.add_argument(
        "--provider", default="claude", choices=["codex", "claude"],
        help="Provider to use (default: claude)",
    )
    exec_p.add_argument("--prompt", required=True, help="Prompt to execute")
    exec_p.add_argument("--workdir", default=".", help="Working directory")
    exec_p.add_argument("--model", default=None, help="Model override")
    exec_p.add_argument(
        "--timeout", type=int, default=300, help="Timeout in seconds",
    )
    exec_p.set_defaults(func=cmd_exec)

    launch_p = sub.add_parser("launch", help="Launch codex in a tmux session")
    launch_p.add_argument("--session", required=True, help="Tmux session name")
    launch_p.add_argument("--workdir", default=".", help="Working directory")
    launch_p.set_defaults(func=cmd_launch)

    inject_p = sub.add_parser("inject", help="Inject prompt into tmux session")
    inject_p.add_argument("--session", required=True, help="Tmux session name")
    inject_p.add_argument("--prompt", required=True, help="Prompt to inject")
    inject_p.set_defaults(func=cmd_inject)

    status_p = sub.add_parser("status", help="Check tmux session status")
    status_p.add_argument("--session", required=True, help="Tmux session name")
    status_p.set_defaults(func=cmd_status)

    cmd_p = sub.add_parser("command", help="Get launch command")
    cmd_p.add_argument(
        "--provider", required=True, choices=["codex", "claude"],
        help="Provider to use",
    )
    cmd_p.add_argument(
        "--mode", required=True, choices=["exec", "interactive"],
        help="Launch mode",
    )
    cmd_p.set_defaults(func=cmd_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
