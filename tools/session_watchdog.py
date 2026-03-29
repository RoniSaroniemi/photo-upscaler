"""Session watchdog daemon — detects dead sessions, restarts them, and writes status.

Reads a session manifest, polls tmux session liveness, restarts dead
sessions/processes within budget, and writes an atomic status file.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pid_lock import PidLock

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
METRICS_DIR = os.path.join(PROJECT_DIR, "state", "metrics")

# Idle/stall thresholds (seconds)
IDLE_THRESHOLD = 300    # >5 min no activity → idle
STALL_THRESHOLD = 900   # >15 min no activity → stalled

_shutdown = False
_start_time = None
_events = []
_last_status = {}
_restart_state = {}  # {session_name: {"timestamps": [...], "total": int, "last_restart": str, "last_reason": str}}
MAX_EVENTS = 50
REQUIRED_KEYS = {"project", "watchdog_pid_file", "poll_interval_seconds", "persistent", "ephemeral"}
_cleanup_stats = {"date": "", "orphans_cleaned": 0, "worktrees_removed": 0, "worktrees_preserved": 0}
_orphan_grace = {}  # {session_name: earliest_cleanup_epoch}
_alert_state = {}  # {session_name: last_alert_epoch}
_alert_stats = {"date": "", "alerts_sent": 0, "last_alert_sent": "", "rate_limited": False}
_soft_ttl_alerted = set()  # session names that have already received a soft TTL alert


def _utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True


def _add_event(session, event, details=""):
    global _events
    _events.append({"time": _utcnow(), "session": session, "event": event, "details": details})
    _events = _events[-MAX_EVENTS:]


def get_session_idle_seconds(name, tmux_server):
    """Query #{session_activity} and return idle seconds, or None on failure."""
    cmd = _tmux_cmd(tmux_server) + ["display-message", "-t", name, "-p", "#{session_activity}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        activity_ts = int(result.stdout.strip())
        return int(time.time() - activity_ts)
    except ValueError:
        return None


def classify_idle_status(idle_seconds):
    """Classify session status based on idle time."""
    if idle_seconds is None:
        return "unknown"
    if idle_seconds < IDLE_THRESHOLD:
        return "active"
    elif idle_seconds < STALL_THRESHOLD:
        return "idle"
    else:
        return "stalled"


def _append_metrics_jsonl(filename, records):
    """Append JSONL records to state/metrics/<filename>."""
    os.makedirs(METRICS_DIR, exist_ok=True)
    filepath = os.path.join(METRICS_DIR, filename)
    with open(filepath, "a") as f:
        for record in records:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")


def _metrics_session_filename():
    """Return today's session metrics filename."""
    return "sessions-" + datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"


def load_manifest(path):
    """Read and validate the session manifest."""
    data = json.loads(Path(path).read_text())
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"Manifest missing required keys: {missing}")
    if not isinstance(data["persistent"], list):
        raise ValueError("'persistent' must be an array")
    for i, entry in enumerate(data["persistent"]):
        if "name" not in entry or "type" not in entry:
            raise ValueError(f"persistent[{i}] must have 'name' and 'type'")
        if entry["type"] not in ("agent", "process"):
            raise ValueError(f"persistent[{i}].type must be 'agent' or 'process'")
    if not isinstance(data.get("ephemeral", {}).get("patterns", []), list):
        raise ValueError("ephemeral.patterns must be an array")
    alerting = data.get("alerting")
    if alerting is not None:
        if not isinstance(alerting, dict):
            raise ValueError("'alerting' must be an object")
        for key in ("telegram", "slack"):
            if key in alerting and not isinstance(alerting[key], bool):
                raise ValueError(f"alerting.{key} must be a boolean")
        for key in ("telegram_config", "slack_config"):
            if key in alerting and not isinstance(alerting[key], str):
                raise ValueError(f"alerting.{key} must be a string")
    return data


def _tmux_cmd(tmux_server):
    return ["tmux", "-L", tmux_server] if tmux_server else ["tmux"]


def check_agent_session(name, tmux_server):
    """Check if a tmux agent session is alive."""
    cmd = _tmux_cmd(tmux_server) + ["has-session", "-t", name]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def check_process(name, pid_file):
    """Check if a process is alive via its PID file."""
    try:
        pid = int(Path(pid_file).read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def get_session_age_minutes(name, tmux_server):
    """Get session age in minutes via tmux session_created timestamp."""
    cmd = _tmux_cmd(tmux_server) + ["display-message", "-t", name, "-p", "#{session_created}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        created = int(result.stdout.strip())
        return (time.time() - created) / 60
    except ValueError:
        return None


def detect_ephemeral_sessions(patterns, tmux_server, orphan_ttl):
    """List ephemeral sessions matching patterns with age info."""
    cmd = _tmux_cmd(tmux_server) + ["list-sessions", "-F", "#{session_name} #{session_created}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    now = time.time()
    sessions = []
    for line in result.stdout.strip().splitlines():
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        sname, created_str = parts
        if not any(fnmatch(sname, p) for p in patterns):
            continue
        try:
            age_min = int((now - int(created_str)) / 60)
        except ValueError:
            continue
        sessions.append({"name": sname, "status": "active",
                         "age_minutes": age_min, "ttl_remaining_minutes": orphan_ttl - age_min})
    return sessions


def _get_cleanup_stats():
    """Get cleanup stats, resetting counters if the date has changed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _cleanup_stats["date"] != today:
        _cleanup_stats.update(date=today, orphans_cleaned=0,
                              worktrees_removed=0, worktrees_preserved=0)
    return _cleanup_stats


def _session_has_recent_activity(name, tmux_server):
    """Check if a tmux session has had activity in the last 5 minutes."""
    base = _tmux_cmd(tmux_server)
    result = subprocess.run(
        base + ["display-message", "-t", name, "-p", "#{session_activity}"],
        capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        last_activity = int(result.stdout.strip())
        return (time.time() - last_activity) < 300
    except ValueError:
        return False


def _capture_pane_output(name, tmux_server, lines=20):
    """Capture last N lines of output from a tmux session."""
    base = _tmux_cmd(tmux_server)
    result = subprocess.run(
        base + ["capture-pane", "-t", name, "-p", "-S", str(-lines)],
        capture_output=True, text=True)
    return result.stdout.rstrip() if result.returncode == 0 else ""


def _find_matching_worktree(session_name):
    """Find a git worktree matching the session name suffix.

    Convention: session 'exec-foo' maps to a worktree whose path ends in 'foo'.
    Returns the worktree path or None.
    """
    parts = session_name.split("-", 1)
    if len(parts) < 2 or not parts[1]:
        return None
    suffix = parts[1]
    result = subprocess.run(["git", "worktree", "list"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None
    for line in result.stdout.strip().splitlines():
        fields = line.split()
        if not fields:
            continue
        wt_path = fields[0]
        if suffix in Path(wt_path).name:
            return wt_path
    return None


def _check_ephemeral_ttls(sessions, ephemeral_config, tmux_server, manifest):
    """Check ephemeral sessions against soft/hard TTL thresholds.

    Soft TTL: log warning + optional alert (once per session, not every poll).
    Hard TTL: kill the session and log ttl_expired event.
    """
    soft_ttl = ephemeral_config.get("soft_ttl_minutes")
    hard_ttl = ephemeral_config.get("hard_ttl_minutes")

    if not soft_ttl and not hard_ttl:
        return

    base = _tmux_cmd(tmux_server)

    for session in sessions:
        age = session["age_minutes"]
        name = session["name"]

        if hard_ttl and age >= hard_ttl:
            # Capture last output for audit trail before killing
            last_output = _capture_pane_output(name, tmux_server, lines=20)
            subprocess.run(base + ["kill-session", "-t", name], capture_output=True)
            details = f"age={age}m hard_ttl={hard_ttl}m"
            if last_output:
                truncated = last_output[-500:] if len(last_output) > 500 else last_output
                details += f"\nlast output:\n{truncated}"
            _add_event(name, "ttl_expired", details)
            # Remove from soft alert tracking since session is gone
            _soft_ttl_alerted.discard(name)

        elif soft_ttl and age >= soft_ttl:
            # One-shot alert per session lifetime — don't spam every poll cycle
            if name not in _soft_ttl_alerted:
                _soft_ttl_alerted.add(name)
                _add_event(name, "ttl_soft_breach",
                           f"age={age}m soft_ttl={soft_ttl}m")
                msg = (f"Session `{name}` has been running for {age}m "
                       f"(soft TTL: {soft_ttl}m). Review or it will be "
                       f"killed at {hard_ttl}m." if hard_ttl
                       else f"Session `{name}` has been running for {age}m "
                       f"(soft TTL: {soft_ttl}m). Review recommended.")
                send_alert(msg, manifest, session_name=name)

    # Clean up stale entries for sessions no longer present
    live_names = {s["name"] for s in sessions}
    _soft_ttl_alerted.difference_update(_soft_ttl_alerted - live_names)


def cleanup_orphans(manifest):
    """Clean up orphaned ephemeral sessions that exceed their TTL.

    Returns a dict with daily cleanup stats.
    """
    eph = manifest.get("ephemeral", {})
    patterns = eph.get("patterns", [])
    orphan_ttl = eph.get("orphan_ttl_minutes", 120)
    tmux_server = manifest.get("tmux_server")
    persistent_names = {e["name"] for e in manifest["persistent"]}
    stats = _get_cleanup_stats()

    sessions = detect_ephemeral_sessions(patterns, tmux_server, orphan_ttl)

    for session in sessions:
        name = session["name"]
        age = session["age_minutes"]

        if age <= orphan_ttl:
            continue

        # Never clean persistent sessions
        if name in persistent_names:
            continue

        # Check grace period from previous TTL extension
        if time.time() < _orphan_grace.get(name, 0):
            continue

        # Check for recent activity — extend TTL by 30 min if active
        if _session_has_recent_activity(name, tmux_server):
            _orphan_grace[name] = time.time() + 30 * 60
            _add_event(name, "orphan_ttl_extended",
                       f"session active, TTL extended 30 min (age: {age}m)")
            continue

        # Capture last 20 lines for audit trail
        last_output = _capture_pane_output(name, tmux_server, lines=20)

        # Kill the tmux session
        base = _tmux_cmd(tmux_server)
        subprocess.run(base + ["kill-session", "-t", name], capture_output=True)
        stats["orphans_cleaned"] += 1

        # Check for a matching git worktree
        wt_detail = ""
        wt_path = _find_matching_worktree(name)
        if wt_path:
            porcelain = subprocess.run(
                ["git", "-C", wt_path, "status", "--porcelain"],
                capture_output=True, text=True)
            if porcelain.returncode == 0 and not porcelain.stdout.strip():
                rm = subprocess.run(["git", "worktree", "remove", wt_path],
                                    capture_output=True, text=True)
                if rm.returncode == 0:
                    stats["worktrees_removed"] += 1
                    wt_detail = f", worktree {wt_path} removed"
                else:
                    stats["worktrees_preserved"] += 1
                    wt_detail = f", worktree remove failed: {rm.stderr.strip()}"
            else:
                stats["worktrees_preserved"] += 1
                wt_detail = f", worktree {wt_path} preserved (uncommitted changes)"
                _add_event(name, "worktree_preserved",
                           f"{wt_path} has uncommitted changes")

        # Log cleanup event with captured output
        details = f"orphan killed (age: {age}m, ttl: {orphan_ttl}m){wt_detail}"
        if last_output:
            truncated = last_output[-500:] if len(last_output) > 500 else last_output
            details += f"\nlast output:\n{truncated}"
        _add_event(name, "orphan_cleaned", details)

    # Remove stale grace entries for sessions that no longer exist
    live_names = {s["name"] for s in sessions}
    for gone in [k for k in _orphan_grace if k not in live_names]:
        del _orphan_grace[gone]

    return {
        "orphans_cleaned_today": stats["orphans_cleaned"],
        "worktrees_removed_today": stats["worktrees_removed"],
        "worktrees_preserved_uncommitted": stats["worktrees_preserved"],
    }


def write_status(status_path, status_data):
    """Atomically write status JSON to disk."""
    p = Path(status_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        os.write(fd, json.dumps(status_data, indent=2).encode())
        os.close(fd)
        os.replace(tmp, p)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _get_restart_state(name):
    """Get or initialize restart state for a session."""
    if name not in _restart_state:
        _restart_state[name] = {"timestamps": [], "total": 0, "last_restart": "", "last_reason": ""}
    return _restart_state[name]


def _check_restart_budget(name, max_per_hour):
    """Check if restart budget is available. Returns True if restart is allowed."""
    state = _get_restart_state(name)
    now = time.time()
    cutoff = now - 3600
    state["timestamps"] = [t for t in state["timestamps"] if t > cutoff]
    return len(state["timestamps"]) < max_per_hour


def _restarts_this_hour(name):
    """Count restarts in the sliding 1-hour window."""
    state = _get_restart_state(name)
    now = time.time()
    cutoff = now - 3600
    return sum(1 for t in state["timestamps"] if t > cutoff)


def _get_alert_stats():
    """Get alert stats, resetting counters if the date has changed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _alert_stats["date"] != today:
        _alert_stats.update(date=today, alerts_sent=0, last_alert_sent="",
                            rate_limited=False)
    return _alert_stats


def send_alert(message, manifest, session_name=None, channels=None):
    """Send an alert via Telegram and/or Slack.

    Rate-limited to 1 alert per session per 10 minutes.
    Returns True if alert was sent, False if skipped.
    """
    alerting = manifest.get("alerting", {})
    stats = _get_alert_stats()

    # Rate limiting per session
    if session_name:
        last = _alert_state.get(session_name, 0)
        if (time.time() - last) < 600:
            stats["rate_limited"] = True
            _add_event(session_name, "alert_rate_limited",
                       "alert suppressed (last alert <10 min ago)")
            return False

    # Determine which channels to use
    if channels:
        use_telegram = channels.get("telegram", False)
        use_slack = channels.get("slack", False)
    else:
        use_telegram = alerting.get("telegram", False)
        use_slack = alerting.get("slack", False)

    if not use_telegram and not use_slack:
        return False

    sent = False

    if use_telegram:
        tg_config = alerting.get("telegram_config", ".agent-comms/telegram.json")
        if Path(tg_config).exists():
            try:
                subprocess.run(
                    ["python3", "tools/agent_telegram.py",
                     "--project-config", tg_config,
                     "send", "--role", "CPO", "--message", message],
                    capture_output=True, timeout=30)
                sent = True
            except Exception as e:
                _add_event("alerting", "telegram_failed", str(e))
        else:
            _add_event("alerting", "telegram_skipped",
                       f"config not found: {tg_config}")

    if use_slack:
        slack_config = alerting.get("slack_config", ".agent-comms/slack.json")
        if Path(slack_config).exists():
            try:
                subprocess.run(
                    ["python3", "tools/agent_slack.py",
                     "--project-config", slack_config,
                     "send", "--role", "CPO", "--message", message],
                    capture_output=True, timeout=30)
                sent = True
            except Exception as e:
                _add_event("alerting", "slack_failed", str(e))
        else:
            _add_event("alerting", "slack_skipped",
                       f"config not found: {slack_config}")

    if sent:
        if session_name:
            _alert_state[session_name] = time.time()
        stats["alerts_sent"] += 1
        stats["last_alert_sent"] = _utcnow()
        stats["rate_limited"] = False
        _add_event(session_name or "alerting", "alert_sent",
                   message[:200])

    return sent


def restart_agent_session(entry, manifest, status_info, reason="agent session dead"):
    """Restart a dead agent tmux session with recovery brief injection."""
    name = entry["name"]
    tmux_server = manifest.get("tmux_server")
    max_restarts = entry.get("max_restarts_per_hour", 3)
    restart_cmd = entry.get("restart_command", "")
    recovery_brief = entry.get("recovery_brief", "")
    delay = entry.get("restart_delay_seconds", 15)
    paste_mode = entry.get("paste_mode", "bracketed")

    if not restart_cmd:
        _add_event(name, "restart_skipped", "no restart_command configured")
        return

    # 1. Check budget
    if not _check_restart_budget(name, max_restarts):
        status_info["status"] = "failed_budget_exhausted"
        _add_event(name, "restart_budget_exhausted",
                   f"{_restarts_this_hour(name)}/{max_restarts} restarts used this hour")
        send_alert(
            f"Session {name} crashed {_restarts_this_hour(name)} times in 1 hour. "
            f"Auto-restart stopped. Manual investigation needed.",
            manifest, session_name=name,
            channels={"telegram": True, "slack": True})
        return

    base = _tmux_cmd(tmux_server)

    # 2. Race condition guard — check if tmux session already exists
    has_session = subprocess.run(base + ["has-session", "-t", name],
                                capture_output=True).returncode == 0
    if has_session:
        # Session exists but Claude isn't running — send restart command into existing session
        _add_event(name, "restart_reuse_session", "tmux session exists, sending restart command")
        subprocess.run(base + ["send-keys", "-t", name, restart_cmd, "Enter"],
                       capture_output=True)
    else:
        # 3. Create tmux session
        subprocess.run(base + ["new-session", "-d", "-s", name, "-x", "220", "-y", "50"],
                       capture_output=True)
        # 4. Launch agent
        subprocess.run(base + ["send-keys", "-t", name, restart_cmd, "Enter"],
                       capture_output=True)

    # 5. Wait for agent to initialize
    time.sleep(delay)

    # 6. Inject recovery brief via bracketed paste
    if recovery_brief:
        brief_content = f"Read {recovery_brief} for your full operating procedures and resume operations."
        load_proc = subprocess.run(
            base + ["load-buffer", "-b", "watchdog-recovery", "-"],
            input=brief_content.encode(), capture_output=True)

        if load_proc.returncode == 0:
            if paste_mode == "bracketed":
                subprocess.run(base + ["paste-buffer", "-p", "-d", "-b", "watchdog-recovery",
                                       "-t", name], capture_output=True)
                time.sleep(0.3)
                subprocess.run(base + ["send-keys", "-t", name, "Enter"], capture_output=True)
            else:
                # legacy mode
                subprocess.run(base + ["paste-buffer", "-d", "-b", "watchdog-recovery",
                                       "-t", name], capture_output=True)
                time.sleep(2)
                subprocess.run(base + ["send-keys", "-t", name, "Enter"], capture_output=True)
                time.sleep(2)
                subprocess.run(base + ["send-keys", "-t", name, "Enter"], capture_output=True)

    # 7. Verify injection
    time.sleep(3)
    cap = subprocess.run(base + ["capture-pane", "-t", name, "-p", "-S", "-5"],
                         capture_output=True, text=True)
    if cap.returncode == 0 and cap.stdout.strip():
        # Check for signs paste is pending — send extra Enter if needed
        pane_text = cap.stdout.strip()
        if pane_text.endswith(">") or "paste" in pane_text.lower():
            subprocess.run(base + ["send-keys", "-t", name, "Enter"], capture_output=True)

    # 8. Update restart state
    state = _get_restart_state(name)
    state["timestamps"].append(time.time())
    state["total"] += 1
    state["last_restart"] = _utcnow()
    state["last_reason"] = reason

    # 9. Update status and log
    status_info["status"] = "restarted"
    _add_event(name, "restarted",
               f"agent session restarted — {reason} (attempt {state['total']}, "
               f"{_restarts_this_hour(name)}/{max_restarts} this hour)")

    # 10. Alert on repeated restarts (2nd+ this hour)
    restarts = _restarts_this_hour(name)
    if restarts >= 2:
        send_alert(
            f"Session {name} restarted again ({restarts} times this hour). "
            f"May be unstable.",
            manifest, session_name=name)


def restart_process(entry, manifest, status_info):
    """Restart a dead process via its restart_command."""
    name = entry["name"]
    max_restarts = entry.get("max_restarts_per_hour", 3)
    restart_cmd = entry.get("restart_command", "")
    pid_file = entry.get("pid_file", "")

    if not restart_cmd:
        _add_event(name, "restart_skipped", "no restart_command configured")
        return

    # 1. Check budget
    if not _check_restart_budget(name, max_restarts):
        status_info["status"] = "failed_budget_exhausted"
        _add_event(name, "restart_budget_exhausted",
                   f"{_restarts_this_hour(name)}/{max_restarts} restarts used this hour")
        send_alert(
            f"Session {name} crashed {_restarts_this_hour(name)} times in 1 hour. "
            f"Auto-restart stopped. Manual investigation needed.",
            manifest, session_name=name,
            channels={"telegram": True, "slack": True})
        return

    # 2. Check PID lock — if another instance is running, skip
    if pid_file:
        try:
            pid = int(Path(pid_file).read_text().strip())
            os.kill(pid, 0)
            # Process is actually alive — race condition
            _add_event(name, "restart_skipped", f"PID {pid} is still alive (race condition)")
            return
        except (OSError, ValueError, FileNotFoundError):
            pass  # PID file missing or process dead — proceed with restart

    # 3. Run restart command as detached subprocess
    log_path = str(Path(pid_file).parent / f"{name}-restart.log") if pid_file else f"/tmp/{name}-restart.log"
    log_dir = Path(log_path).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    log_fd = open(log_path, "a")
    try:
        subprocess.Popen(restart_cmd, shell=True, start_new_session=True,
                         stdout=log_fd, stderr=log_fd)
    finally:
        log_fd.close()

    # 4. Wait up to 10 seconds for PID file to appear/update
    alive = False
    if pid_file:
        for _ in range(10):
            time.sleep(1)
            try:
                new_pid = int(Path(pid_file).read_text().strip())
                os.kill(new_pid, 0)
                alive = True
                break
            except (OSError, ValueError, FileNotFoundError):
                continue
    else:
        time.sleep(2)
        alive = True  # No PID file to verify — assume success

    # 5/6. Check result
    if not alive:
        status_info["status"] = "restart_failed"
        _add_event(name, "restart_failed", "process not alive after 10s wait")
        send_alert(
            f"Failed to restart {name}. Restart command may be wrong "
            f"or environment broken.",
            manifest, session_name=name)
        return

    # 7. Update restart state and log
    state = _get_restart_state(name)
    state["timestamps"].append(time.time())
    state["total"] += 1
    state["last_restart"] = _utcnow()
    state["last_reason"] = "process dead"

    status_info["status"] = "restarted"
    _add_event(name, "restarted",
               f"process restarted (attempt {state['total']}, "
               f"{_restarts_this_hour(name)}/{max_restarts} this hour)")

    # Alert on repeated restarts (2nd+ this hour)
    restarts = _restarts_this_hour(name)
    if restarts >= 2:
        send_alert(
            f"Session {name} restarted again ({restarts} times this hour). "
            f"May be unstable.",
            manifest, session_name=name)


def poll_once(manifest):
    """Run a single poll cycle. Returns status dict."""
    global _last_status
    tmux_server = manifest.get("tmux_server")
    sessions = {}
    for entry in manifest["persistent"]:
        name, etype = entry["name"], entry["type"]
        alive = (check_agent_session(name, tmux_server) if etype == "agent"
                 else check_process(name, entry.get("pid_file", "")))
        status = "healthy" if alive else "dead"
        prev = _last_status.get(name)
        now_ts = _utcnow()
        info = {"type": etype, "status": status, "critical": entry.get("critical", False)}

        # Idle/stall detection for agent sessions
        idle_s = None
        idle_status = "unknown"
        if alive and etype == "agent":
            idle_s = get_session_idle_seconds(name, tmux_server)
            idle_status = classify_idle_status(idle_s)
        elif not alive:
            idle_status = "dead"
        info["idle_seconds"] = idle_s
        info["idle_status"] = idle_status

        if alive:
            info["last_seen_healthy"] = now_ts
            if prev and prev.get("status") == "dead":
                _add_event(name, "detected_healthy", f"{etype} session recovered")
        else:
            info["last_seen_healthy"] = prev.get("last_seen_healthy", "") if prev else ""
            if not prev or prev.get("status") != "dead":
                info["dead_since"] = now_ts
                _add_event(name, "detected_dead", f"{etype} session not alive")
            else:
                info["dead_since"] = prev.get("dead_since", now_ts)
        # Check for reset markers (from cmd_reset)
        reset_dir = Path(manifest["watchdog_pid_file"]).parent / "resets"
        reset_file = reset_dir / name
        if reset_file.exists():
            _restart_state[name] = {"timestamps": [], "total": 0, "last_restart": "", "last_reason": ""}
            reset_file.unlink()
            _add_event(name, "budget_reset", "manual reset via CLI")

        # Proactive age-based restart for healthy agent sessions
        if alive and etype == "agent" and entry.get("max_session_age_minutes"):
            age = get_session_age_minutes(name, tmux_server)
            if age is not None and age > entry["max_session_age_minutes"]:
                _add_event(name, "proactive_refresh",
                           f"age {int(age)}m exceeded max {entry['max_session_age_minutes']}m")
                # Kill existing session so restart creates a fresh one
                base = _tmux_cmd(tmux_server)
                subprocess.run(base + ["kill-session", "-t", name], capture_output=True)
                restart_agent_session(entry, manifest, info,
                                      reason="proactive_context_refresh")
                alive = False  # Session was restarted, skip dead-restart below

        # Attempt restart if dead and restart_command is configured
        if status == "dead" and entry.get("restart_command"):
            if etype == "agent":
                restart_agent_session(entry, manifest, info)
            elif etype == "process":
                restart_process(entry, manifest, info)

        # Add extended restart status fields
        state = _get_restart_state(name)
        info["restarts_this_hour"] = _restarts_this_hour(name)
        info["last_restart"] = state["last_restart"]
        info["last_restart_reason"] = state["last_reason"]
        info["total_restarts"] = state["total"]
        info["restart_history"] = [
            {"time": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "reason": state["last_reason"]}
            for t in state["timestamps"]
        ]
        if info["status"] == "failed_budget_exhausted":
            info["budget_exhausted_at"] = now_ts
            info["requires_manual_intervention"] = True

        sessions[name] = info
        _last_status[name] = info

    # Orphan cleanup — after persistent checks, before building final status
    cleanup_stats = cleanup_orphans(manifest)

    # Soft/hard TTL checks for ephemeral sessions
    eph = manifest.get("ephemeral", {})
    eph_sessions = detect_ephemeral_sessions(eph.get("patterns", []), tmux_server,
                                              eph.get("orphan_ttl_minutes", 120))
    _check_ephemeral_ttls(eph_sessions, eph, tmux_server, manifest)

    # Re-detect after TTL kills may have removed sessions
    eph_sessions = detect_ephemeral_sessions(eph.get("patterns", []), tmux_server,
                                              eph.get("orphan_ttl_minutes", 120))
    for es in eph_sessions:
        sessions[es["name"]] = {"type": "ephemeral", "status": es["status"],
                                 "age_minutes": es["age_minutes"],
                                 "ttl_remaining_minutes": es["ttl_remaining_minutes"]}
    # Sync agent registry with tmux reality
    try:
        from agent_registry import sync_registry
        sync_registry(tmux_server)
    except Exception:
        pass  # Registry sync failure must not affect watchdog

    # Append JSONL time-series metrics
    now_iso = _utcnow()
    metrics_records = []
    for sname, sinfo in sessions.items():
        age = get_session_age_minutes(sname, tmux_server) if sinfo["type"] == "agent" else None
        metrics_records.append({
            "ts": now_iso,
            "session": sname,
            "status": sinfo.get("idle_status", sinfo.get("status", "unknown")),
            "idle_s": sinfo.get("idle_seconds"),
            "age_min": int(age) if age is not None else None,
            "restarts": sinfo.get("total_restarts", 0),
        })
    if metrics_records:
        try:
            _append_metrics_jsonl(_metrics_session_filename(), metrics_records)
        except OSError:
            pass  # Metrics write failure must not affect watchdog

    alert_stats = _get_alert_stats()
    uptime = int((time.time() - _start_time) / 60) if _start_time else 0
    return {"watchdog_pid": os.getpid(), "project": manifest["project"],
            "last_check": _utcnow(), "uptime_minutes": uptime,
            "poll_interval_seconds": manifest["poll_interval_seconds"],
            "sessions": sessions, "recent_events": list(_events),
            "cleanup_stats": cleanup_stats,
            "alerting": {
                "last_alert_sent": alert_stats["last_alert_sent"],
                "alerts_sent_today": alert_stats["alerts_sent"],
                "alert_rate_limited": alert_stats["rate_limited"],
            }}


def poll_loop(manifest):
    """Main loop: poll every interval until shutdown."""
    interval = manifest["poll_interval_seconds"]
    _add_event("watchdog", "watchdog_started", f"PID {os.getpid()}")
    status_path = str(Path(manifest["watchdog_pid_file"]).parent / "session_status.json")
    while not _shutdown:
        try:
            manifest = load_manifest(manifest["_path"]) if "_path" in manifest else manifest
        except Exception as e:
            print(f"[watchdog] manifest reload failed: {e}", file=sys.stderr)
        status = poll_once(manifest)
        write_status(status_path, status)
        healthy = sum(1 for s in status["sessions"].values() if s["status"] in ("healthy", "active"))
        print(f"[watchdog] poll at {status['last_check']} — {healthy}/{len(status['sessions'])} healthy")
        for _ in range(interval):
            if _shutdown:
                break
            time.sleep(1)
    _add_event("watchdog", "watchdog_stopped", f"PID {os.getpid()}")
    write_status(status_path, poll_once(manifest))


# -- Subcommands -------------------------------------------------------------

def cmd_run(manifest_path):
    """Run the watchdog in the foreground."""
    global _start_time
    _start_time = time.time()
    manifest = load_manifest(manifest_path)
    manifest["_path"] = manifest_path
    lock = PidLock(manifest["watchdog_pid_file"])
    if not lock.acquire():
        print(f"ERROR: Another watchdog is already running (see {manifest['watchdog_pid_file']})", file=sys.stderr)
        sys.exit(1)
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    try:
        print(f"[watchdog] started — PID {os.getpid()}, polling every {manifest['poll_interval_seconds']}s")
        poll_loop(manifest)
    finally:
        lock.release()
        print("[watchdog] stopped — lock released")


def cmd_start(manifest_path):
    """Start the watchdog as a detached background process."""
    manifest = load_manifest(manifest_path)
    if PidLock.is_locked(manifest["watchdog_pid_file"]):
        print("ERROR: Watchdog is already running", file=sys.stderr)
        sys.exit(1)
    log_path = str(Path(manifest["watchdog_pid_file"]).parent / "watchdog.log")
    log_fd = open(log_path, "a")
    proc = subprocess.Popen(
        [sys.executable, __file__, "--manifest", manifest_path, "run"],
        stdout=log_fd, stderr=log_fd, preexec_fn=os.setsid,
    )
    log_fd.close()
    print(f"Watchdog started — PID {proc.pid}, log at {log_path}")


def cmd_stop(manifest_path):
    """Stop a running watchdog by sending SIGTERM."""
    manifest = load_manifest(manifest_path)
    pid_path = Path(manifest["watchdog_pid_file"])
    if not pid_path.exists():
        print("No PID file found — watchdog may not be running.")
        return
    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to watchdog PID {pid}")
    except ProcessLookupError:
        print(f"Process {pid} not found — cleaning up stale PID file")
        pid_path.unlink(missing_ok=True)
    except (OSError, ValueError) as e:
        print(f"Error stopping watchdog: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_status(manifest_path):
    """Read and display the current status file."""
    manifest = load_manifest(manifest_path)
    status_path = Path(manifest["watchdog_pid_file"]).parent / "session_status.json"
    if not status_path.exists():
        print("No status file found — watchdog may not be running.")
        return
    data = json.loads(status_path.read_text())
    print(f"Project: {data['project']}")
    print(f"Last check: {data['last_check']}  (uptime {data['uptime_minutes']}m)")
    print(f"Poll interval: {data['poll_interval_seconds']}s")
    print()
    for name, info in data["sessions"].items():
        parts = [info["status"].upper()]
        if info.get("critical"):
            parts.append("CRITICAL")
        if info.get("requires_manual_intervention"):
            parts.append("REQUIRES MANUAL INTERVENTION")
        if info.get("dead_since"):
            parts.append(f"dead since {info['dead_since']}")
        if info.get("age_minutes") is not None:
            parts.append(f"age {info['age_minutes']}m, ttl {info.get('ttl_remaining_minutes', '?')}m")
        total = info.get("total_restarts", 0)
        this_hour = info.get("restarts_this_hour", 0)
        if total > 0 or this_hour > 0:
            parts.append(f"restarts: {this_hour}/hr, {total} total")
        if info.get("last_restart"):
            parts.append(f"last restart: {info['last_restart']}")
        print(f"  {name} ({info['type']}): {' | '.join(parts)}")
    events = data.get("recent_events", [])
    if events:
        print(f"\nRecent events (last {min(5, len(events))} of {len(events)}):")
        for ev in events[-5:]:
            print(f"  [{ev['time']}] {ev['session']}: {ev['event']} — {ev['details']}")


def cmd_reset(manifest_path, session_name):
    """Reset restart budget for a session, allowing auto-restart to resume."""
    manifest = load_manifest(manifest_path)
    # Find the session in manifest to validate it exists
    found = False
    for entry in manifest["persistent"]:
        if entry["name"] == session_name:
            found = True
            break
    if not found:
        print(f"ERROR: Session '{session_name}' not found in manifest", file=sys.stderr)
        sys.exit(1)

    # Clear restart state in the status file
    status_path = Path(manifest["watchdog_pid_file"]).parent / "session_status.json"
    if status_path.exists():
        data = json.loads(status_path.read_text())
        if session_name in data.get("sessions", {}):
            session = data["sessions"][session_name]
            session["status"] = "dead"  # Reset from failed_budget_exhausted to dead
            session["restarts_this_hour"] = 0
            session.pop("budget_exhausted_at", None)
            session.pop("requires_manual_intervention", None)
            if "restart_history" in session:
                session["restart_history"] = []
            write_status(str(status_path), data)

    # Write a reset marker file that the running watchdog can check
    reset_dir = Path(manifest["watchdog_pid_file"]).parent / "resets"
    reset_dir.mkdir(parents=True, exist_ok=True)
    (reset_dir / session_name).write_text(_utcnow())

    print(f"Budget reset for '{session_name}' — auto-restart will resume on next poll cycle")


def cmd_check(manifest_path):
    """Run a single poll cycle and exit."""
    global _start_time
    _start_time = time.time()
    manifest = load_manifest(manifest_path)
    status = poll_once(manifest)
    status_path = str(Path(manifest["watchdog_pid_file"]).parent / "session_status.json")
    write_status(status_path, status)
    for name, info in status["sessions"].items():
        flag = " [CRITICAL]" if info.get("critical") else ""
        print(f"  {name}: {info['status']}{flag}")
    print(f"Status written to {status_path}")


# -- CLI ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Session watchdog daemon")
    parser.add_argument("--manifest", required=True, help="Path to session-manifest.json")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run watchdog in foreground")
    sub.add_parser("start", help="Start watchdog as background process")
    sub.add_parser("stop", help="Stop running watchdog (SIGTERM)")
    sub.add_parser("status", help="Show current session status")
    sub.add_parser("check", help="Single poll cycle, then exit")
    reset_parser = sub.add_parser("reset", help="Reset restart budget for a session")
    reset_parser.add_argument("session_name", help="Session name to reset")
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    if args.command == "reset":
        cmd_reset(args.manifest, args.session_name)
    else:
        {"run": cmd_run, "start": cmd_start, "stop": cmd_stop,
         "status": cmd_status, "check": cmd_check}[args.command](args.manifest)


if __name__ == "__main__":
    main()
