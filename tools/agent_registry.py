#!/usr/bin/env python3
"""Per-project agent registry — tracks running agents, roles, providers, status.

Usage:
    python3 tools/agent_registry.py register --agent-id ID --role ROLE --provider PROVIDER --tmux-session SESSION [opts]
    python3 tools/agent_registry.py update --agent-id ID [--status STATUS] [--accepts-messages BOOL]
    python3 tools/agent_registry.py remove --agent-id ID
    python3 tools/agent_registry.py list [--role ROLE] [--status STATUS] [--json]
    python3 tools/agent_registry.py sync [--json]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
REGISTRY_PATH = os.path.join(PROJECT_DIR, "state", "agent-registry.json")
METRICS_DIR = os.path.join(PROJECT_DIR, "state", "metrics")

VALID_ROLES = ("cpo", "director", "supervisor", "executor", "subconscious", "orchestrator", "panelist", "observer")
VALID_STATUSES = ("active", "idle", "dead", "completed")
VALID_PROVIDERS = ("claude", "codex")


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_registry() -> dict:
    """Load registry from disk, returning empty structure if missing."""
    try:
        with open(REGISTRY_PATH) as f:
            data = json.load(f)
        if "agents" not in data:
            data["agents"] = []
        return data
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "agents": []}


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


def _find_agent(agents: list, agent_id: str):
    """Return (index, agent_dict) or (None, None)."""
    for i, a in enumerate(agents):
        if a.get("agent_id") == agent_id:
            return i, a
    return None, None


def _emit_lifecycle_event(event: str, agent_id: str, **kwargs) -> None:
    """Append a lifecycle event to state/metrics/agents-YYYY-MM-DD.jsonl."""
    try:
        os.makedirs(METRICS_DIR, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = os.path.join(METRICS_DIR, f"agents-{today}.jsonl")
        record = {"ts": _utcnow(), "event": event, "agent_id": agent_id}
        record.update(kwargs)
        with open(filepath, "a") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        pass  # Metrics write failure must not affect registry operations


def _tmux_session_alive(session: str, server: str = None) -> bool:
    """Check if a tmux session exists."""
    cmd = ["tmux"]
    if server:
        cmd += ["-L", server]
    cmd += ["has-session", "-t", session]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=5)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_register(args) -> int:
    data = _load_registry()
    idx, existing = _find_agent(data["agents"], args.agent_id)
    if existing:
        print(f"Agent '{args.agent_id}' already registered — updating.",
              file=sys.stderr)
        existing.update({
            "role": args.role,
            "provider": args.provider,
            "status": "active",
            "tmux_session": args.tmux_session,
            "tmux_server": args.tmux_server,
            "launched_at": _utcnow(),
            "launched_by": args.launched_by or "manual",
            "brief_ref": args.brief_ref,
            "accepts_messages": args.accepts_messages,
        })
    else:
        data["agents"].append({
            "agent_id": args.agent_id,
            "role": args.role,
            "provider": args.provider,
            "status": "active",
            "tmux_session": args.tmux_session,
            "tmux_server": args.tmux_server,
            "launched_at": _utcnow(),
            "launched_by": args.launched_by or "manual",
            "brief_ref": args.brief_ref,
            "accepts_messages": args.accepts_messages,
        })
    _save_registry(data)
    _emit_lifecycle_event("agent_started", args.agent_id,
                          role=args.role, provider=args.provider)
    print(f"Registered agent '{args.agent_id}' (role={args.role}, provider={args.provider})")
    return 0


def cmd_update(args) -> int:
    data = _load_registry()
    idx, agent = _find_agent(data["agents"], args.agent_id)
    if agent is None:
        print(f"Agent '{args.agent_id}' not found.", file=sys.stderr)
        return 1
    old_status = agent.get("status")
    if args.status:
        agent["status"] = args.status
    if args.accepts_messages is not None:
        agent["accepts_messages"] = args.accepts_messages
    _save_registry(data)
    if args.status and args.status != old_status:
        _emit_lifecycle_event("status_changed", args.agent_id,
                              old_status=old_status, new_status=args.status)
    print(f"Updated agent '{args.agent_id}'")
    return 0


def cmd_remove(args) -> int:
    data = _load_registry()
    idx, agent = _find_agent(data["agents"], args.agent_id)
    if agent is None:
        print(f"Agent '{args.agent_id}' not found.", file=sys.stderr)
        return 1
    # Compute duration if launched_at is available
    duration_min = None
    if agent.get("launched_at"):
        try:
            launched = datetime.strptime(agent["launched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            duration_min = int((datetime.now(timezone.utc) - launched).total_seconds() / 60)
        except (ValueError, TypeError):
            pass
    outcome = agent.get("status", "unknown")
    data["agents"].pop(idx)
    _save_registry(data)
    _emit_lifecycle_event("agent_stopped", args.agent_id,
                          duration_min=duration_min, outcome=outcome,
                          role=agent.get("role"))
    print(f"Removed agent '{args.agent_id}'")
    return 0


def cmd_list(args) -> int:
    data = _load_registry()
    agents = data["agents"]
    if args.role:
        agents = [a for a in agents if a.get("role") == args.role]
    if args.status:
        agents = [a for a in agents if a.get("status") == args.status]
    if args.json:
        print(json.dumps(agents, indent=2))
        return 0
    if not agents:
        print("No agents registered.")
        return 0
    header = f"{'AGENT ID':<28} {'ROLE':<14} {'PROVIDER':<10} {'STATUS':<12} {'LAUNCHED BY':<16} {'LAUNCHED AT'}"
    print(header)
    print("-" * len(header))
    for a in agents:
        print(
            f"{a.get('agent_id', '?'):<28} "
            f"{a.get('role', '?'):<14} "
            f"{a.get('provider', '?'):<10} "
            f"{a.get('status', '?'):<12} "
            f"{a.get('launched_by', '?'):<16} "
            f"{a.get('launched_at', '?')}"
        )
    return 0


def cmd_sync(args) -> int:
    """Check tmux sessions; mark dead agents."""
    data = _load_registry()
    changed = 0
    for agent in data["agents"]:
        if agent.get("status") in ("dead", "completed"):
            continue
        session = agent.get("tmux_session")
        if not session:
            continue
        alive = _tmux_session_alive(session, agent.get("tmux_server"))
        if not alive and agent.get("status") != "dead":
            agent["status"] = "dead"
            changed += 1
            if not (args and getattr(args, "json", False)):
                print(f"Marked '{agent['agent_id']}' as dead (tmux session gone)")
        elif alive and agent.get("status") == "dead":
            agent["status"] = "active"
            changed += 1
            if not (args and getattr(args, "json", False)):
                print(f"Marked '{agent['agent_id']}' as active (tmux session recovered)")
    if changed:
        _save_registry(data)
    if args and getattr(args, "json", False):
        print(json.dumps({"synced": changed, "agents": data["agents"]}, indent=2))
    elif changed == 0:
        print("All agents in sync.")
    return 0


# ---------------------------------------------------------------------------
# Public API for programmatic use (by launch.py, watchdog, etc.)
# ---------------------------------------------------------------------------

def register_agent(agent_id: str, role: str, provider: str,
                   tmux_session: str, tmux_server: str = None,
                   launched_by: str = "manual", brief_ref: str = None,
                   accepts_messages: bool = False) -> None:
    """Register an agent programmatically (no CLI args needed)."""
    data = _load_registry()
    idx, existing = _find_agent(data["agents"], agent_id)
    entry = {
        "agent_id": agent_id,
        "role": role,
        "provider": provider,
        "status": "active",
        "tmux_session": tmux_session,
        "tmux_server": tmux_server,
        "launched_at": _utcnow(),
        "launched_by": launched_by,
        "brief_ref": brief_ref,
        "accepts_messages": accepts_messages,
    }
    if existing:
        data["agents"][idx] = entry
    else:
        data["agents"].append(entry)
    _save_registry(data)
    _emit_lifecycle_event("agent_started", agent_id, role=role, provider=provider)


def update_agent_status(agent_id: str, status: str) -> None:
    """Update an agent's status programmatically."""
    data = _load_registry()
    _, agent = _find_agent(data["agents"], agent_id)
    if agent:
        old_status = agent.get("status")
        agent["status"] = status
        _save_registry(data)
        if status != old_status:
            _emit_lifecycle_event("status_changed", agent_id,
                                  old_status=old_status, new_status=status)


def sync_registry(tmux_server: str = None) -> int:
    """Sync registry with tmux reality. Returns number of changes."""
    data = _load_registry()
    changed = 0
    for agent in data["agents"]:
        if agent.get("status") in ("dead", "completed"):
            continue
        session = agent.get("tmux_session")
        if not session:
            continue
        srv = agent.get("tmux_server") or tmux_server
        alive = _tmux_session_alive(session, srv)
        if not alive:
            agent["status"] = "dead"
            changed += 1
        elif agent.get("status") == "dead" and alive:
            agent["status"] = "active"
            changed += 1
    if changed:
        _save_registry(data)
    return changed


def load_registry() -> dict:
    """Load and return the registry (read-only access for orch.py etc.)."""
    return _load_registry()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="agent_registry",
        description="Per-project agent registry — track running agents.",
    )
    sub = parser.add_subparsers(dest="command")

    # register
    p = sub.add_parser("register", help="Register a new agent")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--role", required=True, choices=VALID_ROLES)
    p.add_argument("--provider", required=True, choices=VALID_PROVIDERS)
    p.add_argument("--tmux-session", required=True)
    p.add_argument("--tmux-server", default=None)
    p.add_argument("--launched-by", default="manual")
    p.add_argument("--brief-ref", default=None)
    p.add_argument("--accepts-messages", action="store_true", default=False)

    # update
    p = sub.add_parser("update", help="Update agent status")
    p.add_argument("--agent-id", required=True)
    p.add_argument("--status", choices=VALID_STATUSES)
    p.add_argument("--accepts-messages", type=lambda v: v.lower() in ("true", "1", "yes"),
                   default=None)

    # remove
    p = sub.add_parser("remove", help="Remove an agent")
    p.add_argument("--agent-id", required=True)

    # list
    p = sub.add_parser("list", help="List agents")
    p.add_argument("--role", choices=VALID_ROLES)
    p.add_argument("--status", choices=VALID_STATUSES)
    p.add_argument("--json", action="store_true")

    # sync
    p = sub.add_parser("sync", help="Sync registry with tmux reality")
    p.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "register": cmd_register,
        "update": cmd_update,
        "remove": cmd_remove,
        "list": cmd_list,
        "sync": cmd_sync,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
