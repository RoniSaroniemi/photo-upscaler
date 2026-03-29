#!/usr/bin/env python3
"""Agent dispatcher — routes inbound messages to the right agent sessions.

Usage:
    python3 tools/agent_dispatcher.py --routing-config .agent-comms/routing.json \
        dispatch --sender-id roni --channel-type telegram --message "hello"
    python3 tools/agent_dispatcher.py --routing-config .agent-comms/routing.json status
    python3 tools/agent_dispatcher.py --routing-config .agent-comms/routing.json cleanup

Stdlib-only. No pip dependencies.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.pid_lock import _pid_alive
except ImportError:
    import sys as _sys; _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
    from pid_lock import _pid_alive


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ROUTING_CONFIG = Path(".agent-comms/routing.json")
DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agent-dispatcher" / "projects"
DEFAULT_TIMEOUT_MINUTES = 30
AGENT_INIT_WAIT_SECONDS = 8

# tmux server isolation — set from routing config on load
_tmux_server: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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




def iso_to_timestamp(iso_str: str) -> float:
    """Parse an ISO timestamp to a Unix timestamp."""
    # Handle both Z suffix and +00:00
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0


# ---------------------------------------------------------------------------
# Lock management
# ---------------------------------------------------------------------------

def locks_dir(project_id: str) -> Path:
    return DEFAULT_DATA_ROOT / project_id / "locks"


def lock_path(project_id: str, profile_id: str) -> Path:
    return locks_dir(project_id) / f"{profile_id}.lock"


def load_lock(project_id: str, profile_id: str) -> dict | None:
    """Load a lock file. Returns None if not found or invalid."""
    path = lock_path(project_id, profile_id)
    if not path.exists():
        return None
    try:
        return load_json(path)
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def write_lock(project_id: str, profile_id: str, data: dict) -> None:
    """Write a lock file."""
    path = lock_path(project_id, profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json(path, data)


def remove_lock(project_id: str, profile_id: str) -> None:
    """Remove a lock file."""
    path = lock_path(project_id, profile_id)
    path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# tmux operations
# ---------------------------------------------------------------------------

def tmux_cmd(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a tmux command, prepending -L <server> when configured."""
    server_flags = ["-L", _tmux_server] if _tmux_server else []
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(["tmux", *server_flags, *args], **kwargs)


def tmux_session_exists(session_name: str) -> bool:
    """Check if a tmux session exists."""
    result = tmux_cmd(["has-session", "-t", session_name])
    return result.returncode == 0


def tmux_create_session(session_name: str, width: int = 220,
                        height: int = 50) -> bool:
    """Create a new detached tmux session."""
    result = tmux_cmd(["new-session", "-d", "-s", session_name,
                       "-x", str(width), "-y", str(height)])
    return result.returncode == 0


def tmux_kill_session(session_name: str) -> bool:
    """Kill a tmux session."""
    result = tmux_cmd(["kill-session", "-t", session_name])
    return result.returncode == 0


def tmux_inject(session_name: str, text: str) -> bool:
    """Inject text into a tmux session (paste + enter)."""
    # Resolve pane
    result = tmux_cmd(["list-panes", "-t", session_name, "-F", "#{pane_id}"])
    if result.returncode != 0:
        return False
    pane_id = result.stdout.strip().split("\n")[0]
    if not pane_id:
        return False

    # Create buffer and paste
    buf_name = f"agent-dispatch-{int(time.time() * 1000)}"
    tmux_cmd(["load-buffer", "-b", buf_name, "-"], input=text)
    tmux_cmd(["paste-buffer", "-p", "-b", buf_name, "-t", pane_id])
    time.sleep(2)
    tmux_cmd(["send-keys", "-t", pane_id, "Enter"])
    # Safety Enter after delay — ensures submission if first Enter fired too early
    time.sleep(2)
    tmux_cmd(["send-keys", "-t", pane_id, "Enter"])
    return True


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def load_routing_table(path: Path) -> dict:
    """Load the routing table config."""
    if not path.exists():
        example = path.with_suffix(".json.example") if path.suffix == ".json" else Path(str(path) + ".example")
        if example.exists():
            raise SystemExit(
                f"Config file not found: {path}\n"
                f"An example config exists at: {example}\n"
                f"To get started:\n"
                f"  cp {example} {path}\n"
                f"Then edit {path} and replace the placeholder values."
            )
        raise SystemExit(f"Missing required config file: {path}")
    config = load_json(path)
    global _tmux_server
    _tmux_server = config.get("tmux_server", "") or ""
    return config


def resolve_route(routing_table: dict, sender_id: str,
                  channel_type: str) -> dict | None:
    """Find the best matching route for a sender.

    Matches against sender_match rules in the routing table.
    Returns the route dict or None if no match (falls back to fallback config).
    """
    routes = routing_table.get("routes", [])

    for route in routes:
        match = route.get("sender_match", {})
        match_type = match.get("type", "")

        # Channel type must match
        if match_type and match_type != channel_type:
            continue

        # Check sender identity fields
        match_fields = {k: v for k, v in match.items() if k != "type"}
        if not match_fields:
            # Wildcard route for this channel type
            return route

        # Check if any match field matches the sender_id
        for field, value in match_fields.items():
            if value == "*" or value == sender_id:
                return route

    return None


# ---------------------------------------------------------------------------
# Agent session management
# ---------------------------------------------------------------------------

def is_agent_running(project_id: str, profile_id: str) -> dict | None:
    """Check if an agent session is running for this profile.

    Returns the lock data if running, None if not.
    """
    lock_data = load_lock(project_id, profile_id)
    if lock_data is None:
        return None

    session_name = lock_data.get("tmux_session", "")
    if not session_name:
        remove_lock(project_id, profile_id)
        return None

    # Check tmux session alive
    if not tmux_session_exists(session_name):
        emit("stale_lock_removed", profile=profile_id,
             session=session_name, reason="tmux session dead")
        remove_lock(project_id, profile_id)
        return None

    return lock_data


def check_timeouts(project_id: str, default_timeout: int) -> int:
    """Check all lock files for timeouts. Returns number of sessions killed."""
    ldir = locks_dir(project_id)
    if not ldir.exists():
        return 0

    killed = 0
    now = time.time()

    for lock_file in ldir.glob("*.lock"):
        try:
            data = load_json(lock_file)
        except (json.JSONDecodeError, OSError):
            lock_file.unlink(missing_ok=True)
            continue

        timeout_minutes = data.get("timeout_minutes", default_timeout)
        last_activity = data.get("last_activity_at", data.get("started_at", ""))
        ts = iso_to_timestamp(last_activity)

        if ts > 0 and (now - ts) > timeout_minutes * 60:
            session_name = data.get("tmux_session", "")
            profile_id = data.get("profile_id", lock_file.stem)
            if session_name:
                tmux_kill_session(session_name)
            lock_file.unlink(missing_ok=True)
            emit("session_timed_out", profile=profile_id,
                 session=session_name, timeout_min=timeout_minutes)
            killed += 1

    return killed


def spawn_agent(project_id: str, route: dict, message: str,
                project_root: str = ".") -> str | None:
    """Spawn a temporary agent session for a route.

    Returns the tmux session name, or None on failure.
    """
    profile_id = route["profile"]
    timestamp = int(time.time())
    session_name = f"dispatch-{profile_id}-{timestamp}"

    # Create tmux session
    if not tmux_create_session(session_name):
        emit("spawn_failed", profile=profile_id, reason="tmux create failed")
        return None

    # Launch claude in the session
    agent_command = route.get("agent_command", "claude --dangerously-skip-permissions")
    tmux_cmd(["send-keys", "-t", session_name, agent_command, "Enter"])

    # Wait for agent to initialize
    init_wait = route.get("init_wait_seconds", AGENT_INIT_WAIT_SECONDS)
    time.sleep(init_wait)

    # Build initial briefing
    briefing_parts = []

    # System prompt reference
    system_prompt_ref = route.get("system_prompt_ref")
    if system_prompt_ref:
        briefing_parts.append(f"Read {system_prompt_ref} for your role and instructions.")

    # Context files
    context_files = route.get("context_files", [])
    for cf in context_files:
        briefing_parts.append(f"Read {cf} for context.")

    # Output channel info
    output_channel = route.get("output_channel", {})
    if output_channel:
        ch_type = output_channel.get("type", "")
        if ch_type == "telegram":
            briefing_parts.append(
                f"When you need to respond, use the telegram-send-message skill "
                f"with role={output_channel.get('role', 'CPO')}.")
        elif ch_type == "slack":
            channel = output_channel.get("channel", "")
            briefing_parts.append(
                f"When you need to respond, use the slack-send-message skill "
                f"to channel {channel}.")

    # The actual message
    briefing_parts.append(f"\nInbound message from user:\n{message}")

    briefing = "\n\n".join(briefing_parts)

    # Inject the briefing
    if not tmux_inject(session_name, briefing):
        emit("inject_failed", profile=profile_id, session=session_name)
        tmux_kill_session(session_name)
        return None

    # Write lock
    lock_data = {
        "profile_id": profile_id,
        "tmux_session": session_name,
        "pid": os.getpid(),
        "started_at": now_iso(),
        "last_activity_at": now_iso(),
        "timeout_minutes": route.get("timeout_minutes",
                                     DEFAULT_TIMEOUT_MINUTES),
        "channel_type": route.get("sender_match", {}).get("type", ""),
        "sender_id": "",  # Will be set by caller
    }
    write_lock(project_id, profile_id, lock_data)

    emit("agent_spawned", profile=profile_id, session=session_name)
    return session_name


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(routing_config: Path, sender_id: str, channel_type: str,
             message: str, project_root: str = ".") -> dict:
    """Main dispatch logic: route a message to the right agent.

    Returns a result dict with status and details.
    """
    routing_table = load_routing_table(routing_config)
    default_timeout = routing_table.get("default_timeout_minutes",
                                        DEFAULT_TIMEOUT_MINUTES)

    # Determine project_id from any available config
    project_id = "default"
    for ch_config_name in ["telegram.json", "slack.json"]:
        ch_config_path = routing_config.parent / ch_config_name
        if ch_config_path.exists():
            try:
                ch_config = load_json(ch_config_path)
                project_id = ch_config.get("project_id", project_id)
                break
            except (json.JSONDecodeError, OSError):
                pass

    # Check timeouts first
    check_timeouts(project_id, default_timeout)

    # Resolve route
    route = resolve_route(routing_table, sender_id, channel_type)
    if route is None:
        fallback = routing_table.get("fallback", {})
        action = fallback.get("action", "ignore")
        if fallback.get("log", False):
            emit("no_route", sender=sender_id, channel=channel_type,
                 action=action)
        return {"status": action, "reason": "no matching route"}

    profile_id = route["profile"]
    mode = route.get("mode", "temporary")

    # Persistent mode: inject into existing session
    if mode == "persistent":
        tmux_session = route.get("tmux_session", "")
        if tmux_session and tmux_session_exists(tmux_session):
            tmux_inject(tmux_session, message)
            return {"status": "injected", "profile": profile_id,
                    "session": tmux_session}
        else:
            emit("persistent_session_missing", profile=profile_id,
                 session=tmux_session)
            return {"status": "error", "reason": "persistent session not running"}

    # Temporary mode: check if agent already running
    lock_data = is_agent_running(project_id, profile_id)
    if lock_data:
        session_name = lock_data["tmux_session"]
        # Update last_activity_at
        lock_data["last_activity_at"] = now_iso()
        write_lock(project_id, profile_id, lock_data)
        # Inject into existing session
        tmux_inject(session_name, message)
        return {"status": "injected", "profile": profile_id,
                "session": session_name, "mode": "existing"}

    # Spawn new temporary agent
    session_name = spawn_agent(project_id, route, message, project_root)
    if session_name:
        # Update lock with sender info
        lock_data = load_lock(project_id, profile_id)
        if lock_data:
            lock_data["sender_id"] = sender_id
            write_lock(project_id, profile_id, lock_data)
        return {"status": "spawned", "profile": profile_id,
                "session": session_name}
    else:
        return {"status": "error", "reason": "failed to spawn agent"}


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_dispatch(args: argparse.Namespace) -> int:
    routing_config = Path(args.routing_config).resolve()
    result = dispatch(
        routing_config=routing_config,
        sender_id=args.sender_id,
        channel_type=args.channel_type,
        message=args.message,
        project_root=args.project_root or ".",
    )

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        status = result.get("status", "error")
        profile = result.get("profile", "?")
        session = result.get("session", "?")
        emit(f"dispatch_result", status=status, profile=profile,
             session=session)

    return 0 if result.get("status") in ("injected", "spawned", "ignore") else 1


def cmd_status(args: argparse.Namespace) -> int:
    routing_config = Path(args.routing_config).resolve()

    # Find project_id
    project_id = "default"
    for ch_config_name in ["telegram.json", "slack.json"]:
        ch_config_path = routing_config.parent / ch_config_name
        if ch_config_path.exists():
            try:
                ch_config = load_json(ch_config_path)
                project_id = ch_config.get("project_id", project_id)
                break
            except (json.JSONDecodeError, OSError):
                pass

    ldir = locks_dir(project_id)
    sessions = []

    if ldir.exists():
        for lock_file in ldir.glob("*.lock"):
            try:
                data = load_json(lock_file)
                session_name = data.get("tmux_session", "")
                alive = tmux_session_exists(session_name) if session_name else False
                data["tmux_alive"] = alive
                sessions.append(data)
            except (json.JSONDecodeError, OSError):
                sessions.append({"file": str(lock_file), "error": "invalid"})

    if args.json_output:
        print(json.dumps(sessions, indent=2))
    else:
        if not sessions:
            print("No active dispatch sessions.")
        else:
            for s in sessions:
                profile = s.get("profile_id", "?")
                session = s.get("tmux_session", "?")
                alive = s.get("tmux_alive", False)
                started = s.get("started_at", "?")
                print(f"  {profile} | session={session} | "
                      f"alive={alive} | started={started}")
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    routing_config = Path(args.routing_config).resolve()
    routing_table = load_routing_table(routing_config)
    default_timeout = routing_table.get("default_timeout_minutes",
                                        DEFAULT_TIMEOUT_MINUTES)

    # Find project_id
    project_id = "default"
    for ch_config_name in ["telegram.json", "slack.json"]:
        ch_config_path = routing_config.parent / ch_config_name
        if ch_config_path.exists():
            try:
                ch_config = load_json(ch_config_path)
                project_id = ch_config.get("project_id", project_id)
                break
            except (json.JSONDecodeError, OSError):
                pass

    # Force-expire: use timeout of 0 to kill everything
    if args.force:
        killed = check_timeouts(project_id, 0)
    else:
        killed = check_timeouts(project_id, default_timeout)

    if args.json_output:
        print(json.dumps({"cleaned": killed}))
    else:
        print(f"Cleaned up {killed} session(s).")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Route inbound messages to agent sessions")
    parser.add_argument("--routing-config", default=str(DEFAULT_ROUTING_CONFIG),
                        help="Path to routing.json")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="Output as JSON")

    sub = parser.add_subparsers(dest="command", required=True)

    p_dispatch = sub.add_parser("dispatch",
                                help="Dispatch a message to the right agent")
    p_dispatch.add_argument("--sender-id", required=True,
                            help="Sender identifier")
    p_dispatch.add_argument("--channel-type", required=True,
                            choices=["telegram", "slack"],
                            help="Source channel type")
    p_dispatch.add_argument("--message", required=True,
                            help="Message text")
    p_dispatch.add_argument("--project-root", default=None,
                            help="Project root directory")

    sub.add_parser("status", help="Show active dispatch sessions")

    p_cleanup = sub.add_parser("cleanup",
                               help="Clean up timed-out sessions")
    p_cleanup.add_argument("--force", action="store_true",
                           help="Kill all sessions regardless of timeout")

    args = parser.parse_args()

    commands = {
        "dispatch": cmd_dispatch,
        "status": cmd_status,
        "cleanup": cmd_cleanup,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
