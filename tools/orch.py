#!/usr/bin/env python3
"""Unified orchestration project management CLI."""
import argparse, json, os, signal, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

MANIFESTS_DIR = Path.home() / ".config" / "orchestration" / "manifests"
ROUTER_STATUS = Path.home() / ".config" / "orchestration" / "router-status.json"
GREEN, RED, YELLOW, RESET = "\033[0;32m", "\033[0;31m", "\033[0;33m", "\033[0m"

def _load_agent_registry(proj_path):
    """Load agent registry for a project (returns agents list or [])."""
    reg_path = Path(proj_path) / "state" / "agent-registry.json"
    try:
        with open(reg_path) as f:
            return json.load(f).get("agents", [])
    except (OSError, json.JSONDecodeError):
        return []

def color(text, c):
    return f"{c}{text}{RESET}" if sys.stdout.isatty() else text

def relative_time(ts_str):
    if not ts_str:
        return "—"
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        secs = int((datetime.now(timezone.utc) - ts).total_seconds())
        if secs < 0: return "just now"
        if secs < 60: return f"{secs}s ago"
        if secs < 3600: return f"{secs // 60} min ago"
        if secs < 86400: return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except (ValueError, TypeError):
        return "—"

def discover_projects():
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    projects = []
    for f in sorted(MANIFESTS_DIR.glob("*.json")):
        try:
            projects.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return projects

def find_project(project_id):
    for p in discover_projects():
        if p.get("project_id") == project_id:
            return p
    return None

def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError, OverflowError):
        return False

def read_json_file(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

def tmux_run(server, args):
    cmd = ["tmux"] + (["-L", server] if server else []) + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

def get_tmux_sessions(manifest):
    server = manifest.get("tmux_server")
    cmd = ["tmux"] + (["-L", server] if server else []) + ["list-sessions", "-F", "#{session_name}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return [l.strip() for l in r.stdout.strip().splitlines() if l.strip()] if r.returncode == 0 else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

def count_tmux_sessions(server):
    cmd = ["tmux"] + (["-L", server] if server else []) + ["list-sessions"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return len([l for l in r.stdout.strip().splitlines() if l.strip()]) if r.returncode == 0 else 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0

def get_cpo_health(project):
    data = read_json_file(Path(project.get("path", "")) / project.get("status_file", "state/session_status.json"))
    if not data: return "unknown", None
    sessions = data.get("sessions", {})
    cpo = sessions.get("cpo") or sessions.get("cpo-forge")
    if not cpo: return "unknown", data
    return cpo.get("status", cpo.get("state", "unknown")), data

def get_watchdog_health(project):
    pid_path = Path(project.get("path", "")) / project.get("watchdog_pid_file", "state/watchdog.pid")
    try:
        pid = int(pid_path.read_text().strip())
        return ("healthy", pid) if pid_alive(pid) else ("dead", pid)
    except (OSError, ValueError):
        return "not running", None

def get_router_status():
    data = read_json_file(ROUTER_STATUS)
    if not data: return "not running", data
    return data.get("status", data.get("state", "unknown")), data

def get_last_check(project):
    data = read_json_file(Path(project.get("path", "")) / project.get("status_file", "state/session_status.json"))
    return relative_time(data.get("last_check")) if data else "—"

def health_color(state):
    s = str(state).lower()
    if s in ("healthy", "running", "alive"): return color(state, GREEN)
    if s in ("dead", "not running", "stopped", "error"): return color(state, RED)
    if s in ("degraded", "restarting", "unknown"): return color(state, YELLOW)
    return state

def project_not_found(pid):
    available = [p.get("project_id") for p in discover_projects()]
    print(f"Error: project '{pid}' not found.")
    if available: print(f"Available projects: {', '.join(available)}")

def session_not_found(name, available):
    print(f"Session '{name}' not found.")
    if available:
        print("Available sessions:")
        for s in available: print(f"  {s}")
    else:
        print("No tmux sessions running.")

# --- status ---

def status_all(args):
    projects = discover_projects()
    if not projects:
        print(f"No projects registered. Add manifests to {MANIFESTS_DIR}/")
        return
    router_state, _ = get_router_status()
    if args.json:
        out = []
        for p in projects:
            cpo_state, _ = get_cpo_health(p)
            wd_state, wd_pid = get_watchdog_health(p)
            out.append({
                "project_id": p.get("project_id"), "display_name": p.get("display_name"),
                "tmux_server": p.get("tmux_server"), "cpo": cpo_state,
                "watchdog": wd_state, "watchdog_pid": wd_pid, "router": router_state,
                "sessions": count_tmux_sessions(p.get("tmux_server")),
                "last_check": get_last_check(p),
            })
        print(json.dumps({"projects": out, "router": router_state}, indent=2))
        return
    header = f"{'PROJECT':<25} {'TMUX':<12} {'CPO':<12} {'WATCHDOG':<14} {'ROUTER':<14} {'SESSIONS':>8}  {'LAST CHECK':<12}"
    print(header)
    print("─" * len(header))
    for p in projects:
        cpo_state, _ = get_cpo_health(p)
        wd_state, _ = get_watchdog_health(p)
        print(
            f"{p.get('display_name', p.get('project_id', '?')):<25} "
            f"{(p.get('tmux_server') or '(default)'):<12} "
            f"{health_color(cpo_state):<21} {health_color(wd_state):<23} "
            f"{health_color(router_state):<23} "
            f"{count_tmux_sessions(p.get('tmux_server')):>8}  {get_last_check(p):<12}"
        )
    print(f"\nRouter: {health_color(router_state)}")

def status_project(args, project_id):
    project = find_project(project_id)
    if not project:
        project_not_found(project_id)
        return 1
    proj_path = Path(project.get("path", ""))
    status_data = read_json_file(proj_path / project.get("status_file", "state/session_status.json"))
    cpo_state, _ = get_cpo_health(project)
    wd_state, wd_pid = get_watchdog_health(project)
    router_state, _ = get_router_status()
    registry_agents = _load_agent_registry(proj_path)
    if args.json:
        print(json.dumps({
            "project_id": project.get("project_id"), "display_name": project.get("display_name"),
            "path": str(proj_path), "tmux_server": project.get("tmux_server"),
            "cpo": cpo_state, "watchdog": {"state": wd_state, "pid": wd_pid},
            "router": router_state, "tmux_sessions": count_tmux_sessions(project.get("tmux_server")),
            "communication_mode": project.get("communication_mode"),
            "sessions": status_data.get("sessions", {}) if status_data else {},
            "agents": registry_agents,
            "events": (status_data.get("events", [])[-10:]) if status_data else [],
        }, indent=2))
        return
    print(f"Project:     {project.get('display_name', project.get('project_id'))}")
    print(f"Path:        {proj_path}")
    print(f"Tmux server: {project.get('tmux_server') or '(default)'}")
    print(f"Router mode: {project.get('communication_mode', '—')}\n")
    sessions = status_data.get("sessions", {}) if status_data else {}
    if sessions:
        sh = f"  {'NAME':<20} {'STATUS':<12} {'UPTIME':<14} {'RESTARTS':>8}  {'TYPE':<10}"
        print(f"Sessions:\n{sh}\n  " + "─" * (len(sh) - 2))
        for name, info in sessions.items():
            status = info.get("status", info.get("state", "unknown"))
            uptime = relative_time(info.get("started_at", info.get("last_restart")))
            restarts = info.get("restarts", info.get("restart_count", 0))
            print(f"  {name:<20} {health_color(status):<21} {uptime:<14} {restarts:>8}  {info.get('type', '—'):<10}")
    else:
        print("Sessions: no session data available")
    if registry_agents:
        print()
        ah = f"  {'AGENT ID':<24} {'ROLE':<14} {'PROVIDER':<10} {'STATUS':<12} {'LAUNCHED BY':<16} {'BRIEF'}"
        print(f"Registered Agents:\n{ah}\n  " + "-" * (len(ah) - 2))
        for a in registry_agents:
            brief = a.get("brief_ref") or "-"
            if len(brief) > 30:
                brief = "..." + brief[-27:]
            print(
                f"  {a.get('agent_id', '?'):<24} "
                f"{a.get('role', '?'):<14} "
                f"{a.get('provider', '?'):<10} "
                f"{a.get('status', '?'):<12} "
                f"{a.get('launched_by', '?'):<16} "
                f"{brief}"
            )
    print()
    wd_extra = f"  (PID {wd_pid})" if wd_pid else ""
    print(f"Watchdog:    {health_color(wd_state)}{wd_extra}")
    if status_data and "poll_interval" in status_data:
        print(f"  Poll interval: {status_data['poll_interval']}s")
    print()
    events = (status_data.get("events", []) if status_data else [])[-10:]
    if events:
        print("Recent events:")
        for ev in events:
            print(f"  [{relative_time(ev.get('timestamp', ev.get('time')))}] {ev.get('message', ev.get('event', str(ev)))}")
    else:
        print("Recent events: none")

def cmd_status(args):
    if getattr(args, "project", None):
        return status_project(args, args.project)
    return status_all(args)

# --- start ---

def cmd_start(args):
    project = find_project(args.project)
    if not project:
        return project_not_found(args.project)
    proj_path = Path(project["path"])
    if not proj_path.is_dir():
        print(f"Error: project path does not exist: {proj_path}")
        return
    wd_state, wd_pid = get_watchdog_health(project)
    if wd_state == "healthy" and not args.force:
        print(f"Watchdog already running (PID {wd_pid})")
        return
    server = project.get("tmux_server")
    manifest_path = proj_path / project.get("session_manifest", "config/session-manifest.json")
    result = tmux_run(server, ["new-session", "-d", "-s", "session-watchdog", "-c", str(proj_path)])
    if result.returncode != 0 and "duplicate session" not in result.stderr:
        print(f"Error creating tmux session: {result.stderr.strip()}")
        return
    tmux_run(server, ["send-keys", "-t", "session-watchdog",
                       f"python3 tools/session_watchdog.py --manifest {manifest_path} run", "Enter"])
    display = project.get("display_name", project.get("project_id"))
    print(f"Starting {display}...")
    status_file = proj_path / project.get("status_file", "state/session_status.json")
    healthy, failed = 0, []
    for _ in range(12):
        time.sleep(5)
        data = read_json_file(status_file)
        if not data: continue
        sess = data.get("sessions", {})
        healthy = sum(1 for s in sess.values() if s.get("status", s.get("state", "")) in ("healthy", "running", "alive"))
        failed = [n for n, s in sess.items() if s.get("status", s.get("state", "")) in ("dead", "error", "stopped")]
        if healthy > 0 and not failed: break
    if healthy > 0 and not failed:
        print(f"Project {display} started. {healthy} sessions healthy.")
    elif healthy > 0:
        print(f"Project started but some sessions failed to come up: {', '.join(failed)}")
    else:
        print(f"Project started. Watchdog launched but no session status yet — check with: orch status {args.project}")

# --- stop ---

def cmd_stop(args):
    project = find_project(args.project)
    if not project:
        return project_not_found(args.project)
    server = project.get("tmux_server")
    proj_path = Path(project["path"])
    pid_str = project.get("project_id")
    if not args.force:
        try:
            answer = input(f"Stop {pid_str}? This will kill all {count_tmux_sessions(server)} sessions. [y/N] ")
        except EOFError:
            answer = ""
        if not answer.strip().lower().startswith("y"):
            print("Aborted.")
            return
    pid_file = proj_path / project.get("watchdog_pid_file", "state/watchdog.pid")
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to watchdog (PID {pid})")
    except (OSError, ValueError):
        print("Watchdog not running or PID file missing, continuing...")
    time.sleep(5)
    if server:
        tmux_run(server, ["kill-server"])
    else:
        tmux_run(None, ["kill-session", "-t", "session-watchdog"])
    print(f"Project {pid_str} stopped.")

# --- attach ---

def cmd_attach(args):
    project = find_project(args.project)
    if not project:
        return project_not_found(args.project)
    available = get_tmux_sessions(project)
    if args.session not in available:
        return session_not_found(args.session, available)
    server = project.get("tmux_server")
    cmd = ["tmux"] + (["-L", server] if server else []) + ["attach", "-t", args.session]
    os.execvp("tmux", cmd)

# --- logs ---

def cmd_logs(args):
    project = find_project(args.project)
    if not project:
        return project_not_found(args.project)
    available = get_tmux_sessions(project)
    if args.session not in available:
        return session_not_found(args.session, available)
    server = project.get("tmux_server")
    def capture(n):
        r = tmux_run(server, ["capture-pane", "-t", args.session, "-p", "-S", f"-{n}"])
        return r.stdout if r.returncode == 0 else ""
    if not args.follow:
        print(capture(args.n), end="")
        return
    print(f"Following {args.project}/{args.session} (Ctrl-C to stop)")
    seen = set()
    try:
        while True:
            for line in capture(args.n).splitlines():
                if line not in seen:
                    seen.add(line)
                    print(line)
            time.sleep(2)
    except KeyboardInterrupt:
        print()

# --- router ---

def router_session_exists():
    return tmux_run("orchestration", ["has-session", "-t", "central-router"]).returncode == 0

def cmd_router_start(args):
    script = Path.cwd() / "tools" / "central_router.py"
    if not script.exists():
        for p in discover_projects():
            c = Path(p["path"]) / "tools" / "central_router.py"
            if c.exists():
                script = c
                break
    if not script.exists():
        print(f"Error: central_router.py not found at {script}")
        return
    if router_session_exists():
        print("Router session already exists.")
        return
    cfg = Path.home() / ".config" / "orchestration" / "router.json"
    r = tmux_run("orchestration", ["new-session", "-d", "-s", "central-router", "-c", str(script.parent.parent)])
    if r.returncode != 0:
        print(f"Error creating router session: {r.stderr.strip()}")
        return
    tmux_run("orchestration", ["send-keys", "-t", "central-router",
                                f"python3 {script} --config {cfg} run", "Enter"])
    print("Starting central router...")
    for _ in range(5):
        time.sleep(2)
        data = read_json_file(ROUTER_STATUS)
        if data:
            print(f"Router started (PID {data.get('pid', '?')})")
            return
    print("Router session launched. Status file not yet written — check with: orch router status")

def cmd_router_stop(args):
    data = read_json_file(ROUTER_STATUS)
    if data and data.get("pid"):
        try:
            os.kill(data["pid"], signal.SIGTERM)
            print(f"Sent SIGTERM to router (PID {data['pid']})")
        except OSError:
            print("Router process not found, cleaning up session...")
    tmux_run("orchestration", ["kill-session", "-t", "central-router"])
    print("Router stopped.")

def cmd_router_status(args):
    data = read_json_file(ROUTER_STATUS)
    session_alive = router_session_exists()
    if args.json:
        print(json.dumps({"status_file": data, "tmux_session": session_alive}, indent=2))
        return
    if not data and not session_alive:
        print("Central router is not running.")
        return
    if data:
        print(f"Router:   {health_color(data.get('status', data.get('state', 'unknown')))}")
        if data.get("pid"):
            print(f"PID:      {data['pid']} ({'alive' if pid_alive(data['pid']) else 'dead'})")
        if data.get("started_at"):
            print(f"Uptime:   {relative_time(data['started_at'])}")
        if data.get("bots"):
            bots = data["bots"]
            print(f"Bots:     {', '.join(bots) if isinstance(bots, list) else bots}")
        if data.get("routes"):
            routes = data["routes"]
            print(f"Routes:   {len(routes) if isinstance(routes, list) else routes}")
        if data.get("messages"):
            msgs = data["messages"]
            if isinstance(msgs, dict):
                for k, v in msgs.items(): print(f"Messages ({k}): {v}")
            else:
                print(f"Messages: {msgs}")
    else:
        print("Status file not found, but tmux session exists.")
    print(f"Tmux:     {'active' if session_alive else 'not found'}")

def cmd_router(args):
    sub = getattr(args, "router_command", None)
    if not sub:
        print("Usage: orch router {start|stop|status}")
        return
    {"start": cmd_router_start, "stop": cmd_router_stop, "status": cmd_router_status}[sub](args)

# --- CLI ---

def build_parser():
    parser = argparse.ArgumentParser(prog="orch", description="Unified orchestration project management")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("status", help="Show project status")
    p.add_argument("project", nargs="?", default=None)
    p = sub.add_parser("start", help="Start a project")
    p.add_argument("project"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("stop", help="Stop a project")
    p.add_argument("project"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("attach", help="Attach to a session")
    p.add_argument("project"); p.add_argument("session", nargs="?", default="cpo")
    p = sub.add_parser("logs", help="View session logs")
    p.add_argument("project"); p.add_argument("session", nargs="?", default="cpo")
    p.add_argument("-n", type=int, default=50); p.add_argument("-f", "--follow", action="store_true")
    p = sub.add_parser("router", help="Manage central router")
    rs = p.add_subparsers(dest="router_command")
    rs.add_parser("start"); rs.add_parser("stop"); rs.add_parser("status")
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    dispatch = {"status": cmd_status, "start": cmd_start, "stop": cmd_stop,
                "attach": cmd_attach, "logs": cmd_logs, "router": cmd_router}
    handler = dispatch.get(args.command)
    if handler: handler(args)
    else: parser.print_help()

if __name__ == "__main__":
    main()
