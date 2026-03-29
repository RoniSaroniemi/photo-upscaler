#!/usr/bin/env python3
"""
Project-scoped Slack gateway for Claude/Codex agents.

Secrets live outside the repo in:
  ~/.config/agent-slack/accounts.json

Project config lives in:
  .agent-comms/slack.json
"""
from __future__ import annotations

import argparse, json, mimetypes, os, signal, stat, subprocess, sys
import tempfile, time, urllib.error, urllib.parse, urllib.request

try:
    from tools.pid_lock import _pid_alive
except ImportError:
    import sys as _sys; _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
    from pid_lock import _pid_alive
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PROJECT_CONFIG = Path(".agent-comms/slack.json")
DEFAULT_ACCOUNT_CONFIG = Path.home() / ".config" / "agent-slack" / "accounts.json"
DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agent-slack" / "projects"
SLACK_API_BASE = "https://slack.com/api"
RECENT_SESSION_SECONDS = 15 * 60
DEFAULT_POLL_INTERVAL = 15
DEFAULT_MIN_INTERVAL_MS = 1100
DEFAULT_RETRY_AFTER_CAP = 30
JSON_DEFAULT_MISSING = object()
IGNORED_SUBTYPES = frozenset({"channel_join", "channel_leave", "channel_topic",
                               "channel_purpose", "bot_message"})

# tmux server isolation — set from project config on load
_tmux_server: str = ""

ROUTER_STATUS_FILE = Path.home() / ".config" / "orchestration" / "router-status.json"


def check_router_alive() -> bool:
    """Check if the central router daemon is running."""
    if not ROUTER_STATUS_FILE.exists():
        return False
    try:
        data = json.loads(ROUTER_STATUS_FILE.read_text(encoding="utf-8"))
        pid = data.get("router_pid")
        if not isinstance(pid, int) or pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except (json.JSONDecodeError, OSError, ProcessLookupError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON on stdin: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Hook payload must be a JSON object")
    return payload


def emit(args: argparse.Namespace, payload: Any, *, default_plain: str | None = None) -> int:
    if getattr(args, "json", False):
        json.dump(payload, sys.stdout, indent=2); sys.stdout.write("\n"); return 0
    if default_plain is not None:
        print(default_plain); return 0
    if isinstance(payload, dict):
        for k, v in payload.items(): print(f"{k}={v}")
        return 0
    if isinstance(payload, list):
        for item in payload:
            print(json.dumps(item, ensure_ascii=True) if isinstance(item, dict) else item)
        return 0
    print(payload); return 0


def load_json_file(path: Path, *, default: Any = JSON_DEFAULT_MISSING) -> Any:
    if not path.exists():
        if default is not JSON_DEFAULT_MISSING: return default
        raise SystemExit(f"Missing required file: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh: return json.load(fh)
    except json.JSONDecodeError as exc:
        if default is not JSON_DEFAULT_MISSING: return default
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        json.dump(payload, fh, indent=2, sort_keys=True); fh.write("\n")
        fh.flush(); os.fsync(fh.fileno()); tmp = Path(fh.name)
    os.replace(tmp, path)


def ensure_account_permissions(path: Path) -> None:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SystemExit(f"{path} must be permission 0600 or stricter")


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def resolve_project_config(path_arg: str | None) -> Path:
    return Path(path_arg).expanduser() if path_arg else DEFAULT_PROJECT_CONFIG


def load_project_config(path_arg: str | None) -> tuple[Path, dict[str, Any]]:
    path = resolve_project_config(path_arg)
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
    cfg = load_json_file(path)
    if not isinstance(cfg, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    cfg.setdefault("channel", "main"); cfg.setdefault("enabled_roles", ["CPO"])
    cfg.setdefault("roles", {}); cfg.setdefault("hook_debounce_seconds", 30)
    rate = cfg.setdefault("rate_limit", {})
    if isinstance(rate, dict):
        rate.setdefault("min_interval_ms", DEFAULT_MIN_INTERVAL_MS)
        rate.setdefault("retry_after_cap_seconds", DEFAULT_RETRY_AFTER_CAP)
    global _tmux_server
    _tmux_server = cfg.get("tmux_server", "") or ""
    return path, cfg


def load_accounts(path_arg: str | None = None) -> tuple[Path, dict[str, Any]]:
    path = Path(path_arg).expanduser() if path_arg else DEFAULT_ACCOUNT_CONFIG
    accts = load_json_file(path)
    if not isinstance(accts, dict) or not isinstance(accts.get("accounts"), dict):
        raise SystemExit(f"{path} must contain an accounts object")
    ensure_account_permissions(path)
    return path, accts


def resolve_role_config(pcfg: dict[str, Any], role: str | None) -> tuple[str, dict[str, Any]]:
    roles = pcfg.get("roles", {})
    if role:
        if role not in roles: raise SystemExit(f"Unknown role {role!r} in project config")
        return role, roles[role]
    for r in pcfg.get("enabled_roles", []):
        if r in roles: return r, roles[r]
    if roles:
        r = next(iter(roles)); return r, roles[r]
    raise SystemExit("Project config has no roles configured")


def resolve_account(pcfg: dict[str, Any], acfg: dict[str, Any], name: str | None = None) -> tuple[str, dict[str, Any]]:
    sel = name or pcfg.get("account")
    if not sel: raise SystemExit("No account configured")
    acct = acfg["accounts"].get(sel)
    if not isinstance(acct, dict) or not acct.get("bot_token"):
        raise SystemExit(f"Account {sel!r} is missing or invalid")
    return sel, acct


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _project_id(pcfg: dict[str, Any]) -> str:
    pid = pcfg.get("project_id")
    if not pid: raise SystemExit("Project config must define project_id")
    return pid

def channel_root(pcfg: dict[str, Any], ch: str | None = None) -> Path:
    return DEFAULT_DATA_ROOT / _project_id(pcfg) / (ch or pcfg.get("channel") or "main")

def project_root(pcfg: dict[str, Any]) -> Path:
    return DEFAULT_DATA_ROOT / _project_id(pcfg)

def history_path(pcfg: dict[str, Any], ch: str | None = None) -> Path:
    return channel_root(pcfg, ch) / "history.jsonl"

def state_path(pcfg: dict[str, Any], ch: str | None = None) -> Path:
    return channel_root(pcfg, ch) / "state.json"

def sessions_dir(pcfg: dict[str, Any]) -> Path:
    return project_root(pcfg) / "sessions"

def session_path(pcfg: dict[str, Any], sid: str) -> Path:
    return sessions_dir(pcfg) / f"{sid}.json"

def poller_path(pcfg: dict[str, Any]) -> Path:
    return project_root(pcfg) / "poller.json"

def poller_log_path(pcfg: dict[str, Any]) -> Path:
    return project_root(pcfg) / "poller.log"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state(pcfg: dict[str, Any], ch: str | None = None) -> dict[str, Any]:
    return load_json_file(state_path(pcfg, ch), default={})

def save_state(pcfg: dict[str, Any], st: dict[str, Any], ch: str | None = None) -> None:
    save_json_file(state_path(pcfg, ch), st)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def list_session_records(pcfg: dict[str, Any]) -> list[dict[str, Any]]:
    root = sessions_dir(pcfg)
    if not root.exists(): return []
    recs = [r for p in sorted(root.glob("*.json"))
            for r in [load_json_file(p, default={})] if isinstance(r, dict)]
    recs.sort(key=lambda r: r.get("last_seen_at", ""), reverse=True)
    return recs


def latest_seen_session(pcfg: dict[str, Any], *, allow_stale: bool = False) -> dict[str, Any] | None:
    recs = list_session_records(pcfg)
    if not recs: return None
    if allow_stale: return recs[0]
    cutoff = time.time() - RECENT_SESSION_SECONDS
    for r in recs:
        seen = r.get("last_seen_at")
        if not seen: continue
        try:
            ts = datetime.fromisoformat(seen.replace("Z", "+00:00")).timestamp()
        except ValueError: continue
        if ts >= cutoff: return r
    return None


def resolve_session_id(args: argparse.Namespace, pcfg: dict[str, Any],
                        hook: dict[str, Any] | None = None, *, require: bool = True) -> str | None:
    if getattr(args, "session_id", None): return args.session_id
    if hook and hook.get("session_id"): return str(hook["session_id"])
    for env in ("AGENT_SLACK_SESSION_ID", "CLAUDE_SESSION_ID"):
        if os.environ.get(env): return os.environ[env]
    recent = latest_seen_session(pcfg, allow_stale=getattr(args, "use_latest_seen", False))
    if recent: return recent.get("session_id")
    if require:
        raise SystemExit("No session id available. Use --session-id or wait for hooks to register.")
    return None


def upsert_session_record(pcfg: dict[str, Any], sid: str, updates: dict[str, Any]) -> dict[str, Any]:
    p = session_path(pcfg, sid)
    rec = load_json_file(p, default={})
    if not isinstance(rec, dict): rec = {}
    if not rec:
        rec = {"session_id": sid, "enabled": False, "registered_at": now_iso()}
    rec.update(updates); rec["session_id"] = sid; rec["last_seen_at"] = now_iso()
    save_json_file(p, rec); return rec


def get_session_record(pcfg: dict[str, Any], sid: str | None) -> dict[str, Any] | None:
    if not sid: return None
    p = session_path(pcfg, sid)
    if not p.exists(): return None
    r = load_json_file(p, default=None)
    return r if isinstance(r, dict) else None


# ---------------------------------------------------------------------------
# Poller management
# ---------------------------------------------------------------------------

def load_poller_record(pcfg: dict[str, Any]) -> dict[str, Any] | None:
    p = poller_path(pcfg)
    if not p.exists(): return None
    r = load_json_file(p, default=None)
    return r if isinstance(r, dict) else None

def save_poller_record(pcfg: dict[str, Any], rec: dict[str, Any]) -> None:
    save_json_file(poller_path(pcfg), rec)

def clear_poller_record(pcfg: dict[str, Any]) -> None:
    p = poller_path(pcfg)
    if p.exists(): p.unlink()


def pid_is_running(pid: int | None, *, expected_substrings: list[str] | None = None) -> bool:
    if not pid or pid <= 0: return False
    if not _pid_alive(pid): return False
    if expected_substrings:
        res = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             check=False, capture_output=True, text=True)
        cmd = res.stdout.strip()
        if not cmd or any(f not in cmd for f in expected_substrings): return False
    return True


def poller_runtime_status(pcfg: dict[str, Any]) -> dict[str, Any]:
    rec = load_poller_record(pcfg)
    if not rec: return {"running": False, "record": None}
    try: pid = int(rec["pid"]) if rec.get("pid") is not None else None
    except (TypeError, ValueError): pid = None
    frags = rec.get("command_fragments")
    if not isinstance(frags, list): frags = [str(Path(__file__).resolve()), " poll "]
    running = pid_is_running(pid, expected_substrings=frags)
    rec["running"] = running
    return {"running": running, "record": rec}


def stop_poller_process(pcfg: dict[str, Any]) -> dict[str, Any]:
    st = poller_runtime_status(pcfg); rec = st.get("record")
    if not rec: return {"stopped": False, "reason": "not_configured"}
    pid = rec.get("pid")
    if not st.get("running"):
        clear_poller_record(pcfg); return {"stopped": False, "reason": "not_running", "pid": pid}
    try: os.kill(int(pid), signal.SIGTERM)
    except OSError as exc:
        clear_poller_record(pcfg); return {"stopped": False, "reason": f"kill_failed:{exc}", "pid": pid}
    clear_poller_record(pcfg); return {"stopped": True, "pid": pid}


def start_poller_process(cfg_path: Path, pcfg: dict[str, Any], *,
                          session_id: str, interval: int, channel: str | None) -> dict[str, Any]:
    cur = poller_runtime_status(pcfg); cr = cur.get("record")
    if cur.get("running") and cr:
        if cr.get("session_id") == session_id and int(cr.get("interval", interval)) == interval:
            return {"started": False, "reason": "already_running", "pid": cr.get("pid"),
                    "session_id": session_id, "log_path": cr.get("log_path")}
        stop_poller_process(pcfg)
    cmd = [sys.executable, str(Path(__file__).resolve()), "--project-config",
           str(cfg_path.resolve()), "poll", "--session-id", session_id, "--interval", str(interval)]
    if channel: cmd.extend(["--channel", channel])
    lp = poller_log_path(pcfg); lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT, start_new_session=True,
                                cwd=str(cfg_path.parent.resolve()))
    rec = {"pid": proc.pid, "session_id": session_id, "interval": interval,
           "channel": channel or pcfg.get("channel") or "main", "started_at": now_iso(),
           "log_path": str(lp),
           "command_fragments": [str(Path(__file__).resolve()), " poll ", f"--session-id {session_id}"]}
    save_poller_record(pcfg, rec)
    return {"started": True, "pid": proc.pid, "session_id": session_id,
            "interval": interval, "log_path": str(lp)}


# ---------------------------------------------------------------------------
# History management
# ---------------------------------------------------------------------------

def append_history(pcfg: dict[str, Any], rec: dict[str, Any], ch: str | None = None) -> None:
    p = history_path(pcfg, ch); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=True)); fh.write("\n")


def load_history(pcfg: dict[str, Any], ch: str | None = None) -> list[dict[str, Any]]:
    p = history_path(pcfg, ch)
    if not p.exists(): return []
    recs: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line: continue
            try: e = json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(e, dict): recs.append(e)
    return recs


def save_history(pcfg: dict[str, Any], recs: list[dict[str, Any]], ch: str | None = None) -> None:
    p = history_path(pcfg, ch); p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=p.parent, delete=False) as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=True)); fh.write("\n")
        fh.flush(); os.fsync(fh.fileno()); tmp = Path(fh.name)
    os.replace(tmp, p)


def message_key(rec: dict[str, Any]) -> str:
    return f"{rec.get('direction')}:{rec.get('ts')}"


# ---------------------------------------------------------------------------
# Slack API layer
# ---------------------------------------------------------------------------

def _rate_cfg(pcfg: dict[str, Any] | None) -> tuple[int, int]:
    if not pcfg: return DEFAULT_MIN_INTERVAL_MS, DEFAULT_RETRY_AFTER_CAP
    r = pcfg.get("rate_limit")
    if not isinstance(r, dict): return DEFAULT_MIN_INTERVAL_MS, DEFAULT_RETRY_AFTER_CAP
    return int(r.get("min_interval_ms", DEFAULT_MIN_INTERVAL_MS)), \
           int(r.get("retry_after_cap_seconds", DEFAULT_RETRY_AFTER_CAP))

_last_api_call: float = 0.0


def slack_api_request(token: str, method: str, payload: dict[str, Any] | None = None,
                      *, project_config: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    global _last_api_call
    min_ms, cap = _rate_cfg(project_config)
    elapsed = (time.time() - _last_api_call) * 1000
    if elapsed < min_ms: time.sleep((min_ms - elapsed) / 1000)
    url = f"{SLACK_API_BASE}/{method}"
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    data = json.dumps(payload or {}).encode("utf-8")
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        _last_api_call = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                ra = exc.headers.get("Retry-After")
                wait = min(int(ra) if ra else 1, cap)
                if attempt < 3: time.sleep(wait); continue
                raise SystemExit("Slack API rate limited after retries") from exc
            raise SystemExit(f"Slack API HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"Slack API connection error: {exc}") from exc
        if not isinstance(result, dict):
            raise SystemExit(f"Slack API returned non-object: {result!r}")
        if not result.get("ok"):
            err = result.get("error", "unknown_error")
            if err == "ratelimited" and attempt < 3: time.sleep(min(1, cap)); continue
            raise SystemExit(f"Slack API error: {err} ({json.dumps(result)})")
        return result
    raise SystemExit("Slack API request failed after retries")


def slack_upload_raw(token: str, url: str, data: bytes, *, content_type: str = "application/octet-stream") -> int:
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": content_type}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp: return resp.status
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Slack upload HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Slack upload error: {exc}") from exc


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------

def _ts_to_iso(msg: dict[str, Any]) -> str:
    raw = msg.get("ts")
    if isinstance(raw, str):
        try: return datetime.fromtimestamp(float(raw), timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, OverflowError): pass
    return now_iso()


def build_inbound_record(pcfg: dict[str, Any], channel: str, slack_ch: str, msg: dict[str, Any]) -> dict[str, Any]:
    ts = msg.get("ts", ""); thr = msg.get("thread_ts")
    return {"direction": "inbound", "timestamp": _ts_to_iso(msg), "ts": ts,
            "project_id": pcfg["project_id"], "channel": channel, "agent_name": None,
            "slack_channel": slack_ch, "message_id": ts,
            "thread_ts": thr if thr and thr != ts else None,
            "sender_id": msg.get("user", "unknown"), "sender_label": msg.get("user", "unknown"),
            "text": msg.get("text") or "<non-text message>", "read": False, "media_type": "text"}


def build_outbound_record(pcfg: dict[str, Any], channel: str, agent: str, slack_ch: str,
                           result: dict[str, Any], *, text: str, thread_ts: str | None = None,
                           media_type: str = "text", extras: dict[str, Any] | None = None) -> dict[str, Any]:
    ts = result.get("ts", "")
    rec = {"direction": "outbound", "timestamp": now_iso(), "ts": ts,
           "project_id": pcfg["project_id"], "channel": channel, "agent_name": agent,
           "slack_channel": slack_ch, "message_id": ts, "thread_ts": thread_ts,
           "sender_id": None, "sender_label": agent, "text": text,
           "read": True, "media_type": media_type}
    if extras: rec.update(extras)
    return rec


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def format_record_plain(rec: dict[str, Any]) -> str:
    ts = rec.get("timestamp", ""); d = rec.get("direction", "")
    s = rec.get("sender_label") or rec.get("agent_name") or "unknown"
    return f"{ts} {d} {s}: {rec.get('text', '')}"


def read_message_input(args: argparse.Namespace) -> str:
    msg = args.message
    if getattr(args, "stdin", False):
        si = sys.stdin.read(); msg = si if msg is None else f"{msg}\n{si}"
    if not msg: raise SystemExit("Message text is required")
    return msg.rstrip("\n")


def history_subset(pcfg: dict[str, Any], *, channel_override: str | None,
                   direction: str | None, unread_only: bool = False,
                   limit: int | None = None) -> list[dict[str, Any]]:
    recs = load_history(pcfg, channel_override)
    if direction: recs = [r for r in recs if r.get("direction") == direction]
    if unread_only: recs = [r for r in recs if not r.get("read")]
    recs.sort(key=lambda r: (r.get("timestamp", ""), r.get("ts") or ""), reverse=True)
    if limit is not None: recs = recs[:limit]
    return recs


# ---------------------------------------------------------------------------
# tmux helpers
# ---------------------------------------------------------------------------

def tmux_target(rcfg: dict[str, Any], srec: dict[str, Any] | None) -> str | None:
    if srec and srec.get("tmux_session"): return str(srec["tmux_session"])
    if rcfg.get("tmux_session"): return str(rcfg["tmux_session"])
    return None

def _tmux(a: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    server_flags = ["-L", _tmux_server] if _tmux_server else []
    return subprocess.run(["tmux", *server_flags, *a], check=False, text=True, input=input_text, capture_output=True)

def tmux_notify(target: str, text: str) -> None:
    r = _tmux(["display-message", "-t", target, text])
    if r.returncode: raise SystemExit(f"tmux notify failed: {r.stderr.strip() or r.stdout.strip()}")

def resolve_tmux_pane(target: str) -> str:
    r = _tmux(["display-message", "-p", "-t", target, "#{pane_id}"])
    if r.returncode: raise SystemExit(f"tmux pane resolution failed: {r.stderr.strip()}")
    pane = r.stdout.strip()
    if not pane: raise SystemExit(f"tmux pane resolution returned no pane for {target!r}")
    return pane

def tmux_inject(target: str, text: str) -> None:
    pane = resolve_tmux_pane(target)
    buf = f"agent-slack-{int(time.time() * 1000)}"
    ld = _tmux(["load-buffer", "-b", buf, "-"], input_text=text)
    if ld.returncode: raise SystemExit(f"tmux load-buffer failed: {ld.stderr.strip()}")
    ps = _tmux(["paste-buffer", "-p", "-t", pane, "-b", buf, "-d"])
    if ps.returncode: raise SystemExit(f"tmux paste-buffer failed: {ps.stderr.strip()}")
    time.sleep(2)
    sk = _tmux(["send-keys", "-t", pane, "Enter"])
    if sk.returncode: raise SystemExit(f"tmux send-keys failed: {sk.stderr.strip()}")
    # Safety Enter — ensures submission if first Enter fired before terminal processed the text
    time.sleep(2); _tmux(["send-keys", "-t", pane, "Enter"])


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_messages(pcfg: dict[str, Any], acct: dict[str, Any], *, channel_override: str | None = None) -> dict[str, Any]:
    channel = channel_override or pcfg.get("channel") or "main"
    slack_ch = str(pcfg.get("default_channel") or acct.get("default_channel") or "")
    if not slack_ch: raise SystemExit("No default_channel configured")
    bot_uid = acct.get("bot_user_id", "")
    state = load_state(pcfg, channel_override)
    existing = {message_key(r) for r in load_history(pcfg, channel_override)}
    params: dict[str, Any] = {"channel": slack_ch, "limit": 100}
    last_ts = state.get("last_seen_ts")
    if last_ts: params["oldest"] = last_ts
    all_msgs: list[dict[str, Any]] = []
    has_more = True
    while has_more:
        resp = slack_api_request(acct["bot_token"], "conversations.history", params, project_config=pcfg)
        all_msgs.extend(resp.get("messages", []))
        nc = (resp.get("response_metadata") or {}).get("next_cursor")
        if nc: params["cursor"] = nc
        else: has_more = False
    all_msgs.reverse()  # Slack returns newest-first; we want chronological
    new_recs: list[dict[str, Any]] = []; newest = last_ts or "0"
    for m in all_msgs:
        if bot_uid and m.get("user") == bot_uid: continue
        if m.get("subtype") in IGNORED_SUBTYPES: continue
        mts = m.get("ts", "")
        if last_ts and mts == last_ts: continue
        rec = build_inbound_record(pcfg, channel, slack_ch, m)
        k = message_key(rec)
        if k in existing: continue
        existing.add(k); new_recs.append(rec)
        if mts > newest: newest = mts
    for r in new_recs: append_history(pcfg, r, channel_override)
    if newest > (last_ts or "0"): state["last_seen_ts"] = newest
    state["last_sync_at"] = now_iso(); save_state(pcfg, state, channel_override)
    unread = len([r for r in load_history(pcfg, channel_override)
                  if r.get("direction") == "inbound" and not r.get("read")])
    return {"synced": len(new_recs), "last_seen_ts": state.get("last_seen_ts"),
            "last_sync_at": state.get("last_sync_at"), "unread_count": unread, "records": new_recs}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def latest_unread(recs: list[dict[str, Any]]) -> dict[str, Any] | None:
    u = [r for r in recs if r.get("direction") == "inbound" and not r.get("read")]
    return u[-1] if u else None


def maybe_deliver(pcfg: dict[str, Any], role: str, rcfg: dict[str, Any],
                  srec: dict[str, Any], *, channel_override: str | None = None) -> dict[str, Any]:
    recs = load_history(pcfg, channel_override); latest = latest_unread(recs)
    if latest is None: return {"delivered": False, "reason": "no_unread"}
    state = load_state(pcfg, channel_override)
    deliveries = state.setdefault("deliveries", {})
    rd = deliveries.setdefault(role, {}); rk = message_key(latest)
    if rd.get("last_message_key") == rk:
        return {"delivered": False, "reason": "already_delivered", "message_key": rk}
    mode = rcfg.get("inbound_mode", "notify"); tgt = tmux_target(rcfg, srec)
    txt = str(latest.get("text", "")); thr = latest.get("thread_ts")
    if mode == "inject":
        if not tgt: raise SystemExit(f"Role {role} configured for inject but has no tmux session")
        pfx = f"[Slack][{pcfg['project_id']}/{latest['channel']}]"
        if thr: pfx += f"[thread:{thr}]"
        tmux_inject(tgt, f"{pfx}[{latest['sender_label']}] {txt}")
    else:
        summary = f"Slack message waiting for {pcfg['project_id']}/{latest['channel']} from {latest['sender_label']}"
        if tgt: tmux_notify(tgt, summary)
        else: print(summary)
    rd["last_message_key"] = rk; rd["last_delivered_at"] = now_iso()
    save_state(pcfg, state, channel_override)
    return {"delivered": True, "mode": mode, "message_key": rk, "target": tgt}


# ---------------------------------------------------------------------------
# Hook debounce
# ---------------------------------------------------------------------------

def should_debounce(pcfg: dict[str, Any], hook: dict[str, Any], ch: str | None = None) -> bool:
    if hook.get("hook_event_name") == "SessionStart": return False
    state = load_state(pcfg, ch); lc = state.get("last_hook_check_at")
    if not lc: return False
    try: lt = datetime.fromisoformat(lc.replace("Z", "+00:00")).timestamp()
    except ValueError: return False
    return (time.time() - lt) < int(pcfg.get("hook_debounce_seconds", 30))

def touch_hook_check(pcfg: dict[str, Any], ch: str | None = None) -> None:
    st = load_state(pcfg, ch); st["last_hook_check_at"] = now_iso(); save_state(pcfg, st, ch)


# ---------------------------------------------------------------------------
# CLI command handlers
# ---------------------------------------------------------------------------

def cmd_account_test(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    _, acfg = load_accounts(args.accounts_config)
    aname, acct = resolve_account(pcfg, acfg, args.account)
    r = slack_api_request(acct["bot_token"], "auth.test", project_config=pcfg)
    p = {"account": aname, "bot_user_id": r.get("user_id"), "team": r.get("team"),
         "team_id": r.get("team_id"), "user": r.get("user"), "ok": True}
    return emit(args, p, default_plain=f"ok account={aname} user={r.get('user')} team={r.get('team')}")


def cmd_config_validate(args: argparse.Namespace) -> int:
    pp, pcfg = load_project_config(args.project_config)
    ap, acfg = load_accounts(args.accounts_config)
    aname, acct = resolve_account(pcfg, acfg)
    issues: list[str] = []
    if not pcfg.get("project_id"): issues.append("project_id is required")
    if not pcfg.get("default_channel") and not acct.get("default_channel"):
        issues.append("default_channel required in project or account config")
    if not acct.get("bot_user_id"):
        issues.append("bot_user_id required in account config for filtering")
    for r in pcfg.get("enabled_roles", []):
        if r not in pcfg.get("roles", {}): issues.append(f"enabled role {r!r} has no config")
    for rn, rc in pcfg.get("roles", {}).items():
        if rc.get("inbound_mode") not in (None, "notify", "inject"):
            issues.append(f"role {rn!r} has invalid inbound_mode")
        if rc.get("inbound_mode") == "inject" and not rc.get("tmux_session"):
            issues.append(f"role {rn!r} uses inject but has no tmux_session")
    p = {"project_config": str(pp), "accounts_config": str(ap), "account": aname,
         "issues": issues, "valid": not issues}
    if issues: return emit(args, p, default_plain="invalid\n" + "\n".join(f"- {i}" for i in issues))
    return emit(args, p, default_plain=f"ok project={pcfg['project_id']} account={aname}")


def cmd_send(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    _, acfg = load_accounts(args.accounts_config)
    ch = args.channel or pcfg.get("channel") or "main"
    role, rcfg = resolve_role_config(pcfg, args.role)
    _, acct = resolve_account(pcfg, acfg)
    agent = args.agent_name or rcfg.get("agent_name") or role
    msg = read_message_input(args)
    text = msg if args.raw else f"[{agent}] {msg}"
    if getattr(args, "dm", None):
        dr = slack_api_request(acct["bot_token"], "conversations.open", {"users": args.dm}, project_config=pcfg)
        slack_ch = (dr.get("channel") or {}).get("id")
        if not slack_ch: raise SystemExit(f"Could not open DM with user {args.dm}")
    else:
        slack_ch = str(getattr(args, "target_channel", None) or pcfg.get("default_channel")
                       or acct.get("default_channel") or "")
    if not slack_ch: raise SystemExit("No target channel configured")
    sp: dict[str, Any] = {"channel": slack_ch, "text": text}
    thr = getattr(args, "thread_ts", None)
    if thr: sp["thread_ts"] = thr
    result = slack_api_request(acct["bot_token"], "chat.postMessage", sp, project_config=pcfg)
    rec = build_outbound_record(pcfg, ch, agent, slack_ch, result, text=text, thread_ts=thr)
    append_history(pcfg, rec, ch)
    return emit(args, {"sent": True, "ts": rec["ts"], "channel": slack_ch, "agent_name": agent},
                default_plain=f"sent ts={rec['ts']} channel={slack_ch} agent={agent}")


def cmd_send_file(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    _, acfg = load_accounts(args.accounts_config)
    ch = args.channel or pcfg.get("channel") or "main"
    role, rcfg = resolve_role_config(pcfg, args.role)
    _, acct = resolve_account(pcfg, acfg)
    agent = rcfg.get("agent_name") or role
    fp = Path(args.file).expanduser()
    if not fp.exists(): raise SystemExit(f"File not found: {fp}")
    slack_ch = str(pcfg.get("default_channel") or acct.get("default_channel") or "")
    if not slack_ch: raise SystemExit("No target channel configured")
    caption = args.caption or ""
    # Step 1: get upload URL
    ur = slack_api_request(acct["bot_token"], "files.getUploadURLExternal",
                           {"filename": fp.name, "length": fp.stat().st_size}, project_config=pcfg)
    upload_url, file_id = ur.get("upload_url"), ur.get("file_id")
    if not upload_url or not file_id: raise SystemExit("Failed to get upload URL")
    # Step 2: upload content
    ct = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
    slack_upload_raw(acct["bot_token"], upload_url, fp.read_bytes(), content_type=ct)
    # Step 3: complete
    cp: dict[str, Any] = {"files": [{"id": file_id, "title": caption or fp.name}], "channel_id": slack_ch}
    thr = getattr(args, "thread_ts", None)
    if thr: cp["thread_ts"] = thr
    if caption: cp["initial_comment"] = f"[{agent}] {caption}"
    slack_api_request(acct["bot_token"], "files.completeUploadExternal", cp, project_config=pcfg)
    rec = {"direction": "outbound", "timestamp": now_iso(), "ts": file_id,
           "project_id": pcfg["project_id"], "channel": ch, "agent_name": agent,
           "slack_channel": slack_ch, "message_id": file_id, "thread_ts": thr,
           "sender_id": None, "sender_label": agent, "text": caption or fp.name,
           "read": True, "media_type": "file",
           "file": {"file_id": file_id, "filename": fp.name, "size": fp.stat().st_size}}
    append_history(pcfg, rec, ch)
    return emit(args, {"sent": True, "file_id": file_id, "channel": slack_ch,
                        "agent_name": agent, "media_type": "file"},
                default_plain=f"sent file file_id={file_id} channel={slack_ch} agent={agent}")


def cmd_sync(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    _, acfg = load_accounts(args.accounts_config)
    _, acct = resolve_account(pcfg, acfg)
    p = sync_messages(pcfg, acct, channel_override=args.channel)
    return emit(args, p, default_plain=f"synced={p['synced']} unread={p['unread_count']}")


def cmd_latest(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    recs = history_subset(pcfg, channel_override=args.channel, direction=args.direction, limit=1)
    if not recs: return emit(args, {"message": None}, default_plain="no messages")
    return emit(args, recs[0], default_plain=format_record_plain(recs[0]))


def cmd_history(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    recs = history_subset(pcfg, channel_override=args.channel, direction=args.direction, limit=args.limit)
    if getattr(args, "json", False): return emit(args, recs)
    if not recs: print("no messages"); return 0
    for r in recs: print(format_record_plain(r))
    return 0


def cmd_unread(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    recs = history_subset(pcfg, channel_override=args.channel, direction="inbound",
                          unread_only=True, limit=args.limit)
    if getattr(args, "json", False): return emit(args, recs)
    if not recs: print("no unread messages"); return 0
    for r in recs: print(format_record_plain(r))
    return 0


def cmd_mark_read(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    recs = load_history(pcfg, args.channel); updated = 0
    climit = getattr(args, "count", None)
    for r in recs:
        if r.get("direction") != "inbound" or r.get("read"): continue
        if args.all or (climit is not None and updated < climit):
            r["read"] = True; updated += 1
    save_history(pcfg, recs, args.channel)
    return emit(args, {"updated": updated}, default_plain=f"marked_read={updated}")


def cmd_enable_session(args: argparse.Namespace) -> int:
    pp, pcfg = load_project_config(args.project_config)
    role, rcfg = resolve_role_config(pcfg, args.role)
    sid = resolve_session_id(args, pcfg)
    tgt = args.tmux_session or rcfg.get("tmux_session")
    rec = upsert_session_record(pcfg, sid, {"role": role, "enabled": True, "tmux_session": tgt})
    p: dict[str, Any] = {"session": rec}
    plain = f"enabled session={sid} role={role} tmux={tgt or '-'}"
    if getattr(args, "start_poller", False):
        pol = start_poller_process(pp, pcfg, session_id=sid, interval=args.poll_interval, channel=args.channel)
        p["poller"] = pol
        plain += f" poller_pid={pol['pid']}" if pol.get("started") else f" poller={pol.get('reason')}"
    return emit(args, p, default_plain=plain)


def cmd_disable_session(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    sid = resolve_session_id(args, pcfg)
    rec = upsert_session_record(pcfg, sid, {"enabled": False})
    p: dict[str, Any] = {"session": rec}; plain = f"disabled session={sid}"
    if getattr(args, "stop_poller", False):
        pol = load_poller_record(pcfg)
        if pol and pol.get("session_id") == sid:
            sp = stop_poller_process(pcfg); p["poller"] = sp
            plain += f" poller_stopped={sp.get('stopped')}"
    return emit(args, p, default_plain=plain)


def cmd_session_status(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    if args.all:
        recs = list_session_records(pcfg)
        return emit(args, recs, default_plain=("\n".join(json.dumps(r, ensure_ascii=True) for r in recs) if recs else "no sessions"))
    sid = resolve_session_id(args, pcfg, require=False)
    rec = get_session_record(pcfg, sid) if sid else latest_seen_session(pcfg, allow_stale=True)
    if not rec: return emit(args, {"session": None}, default_plain="no session record")
    return emit(args, rec,
                default_plain=f"session={rec.get('session_id')} enabled={rec.get('enabled')} role={rec.get('role') or '-'} tmux={rec.get('tmux_session') or '-'}")


def cmd_hook_check(args: argparse.Namespace) -> int:
    pp, pcfg = load_project_config(args.project_config)
    _, acfg = load_accounts(args.accounts_config)
    _, acct = resolve_account(pcfg, acfg)
    hp = read_stdin_json() if args.stdin_hook or not sys.stdin.isatty() else {}
    sid = resolve_session_id(args, pcfg, hp, require=False)
    if sid:
        upsert_session_record(pcfg, sid, {"last_hook_event": hp.get("hook_event_name"),
                                           "transcript_path": hp.get("transcript_path"),
                                           "cwd": hp.get("cwd") or str(pp.parent.resolve())})
    if hp.get("hook_event_name") == "Stop" and hp.get("stop_hook_active"):
        return emit(args, {"skipped": "stop_hook_active"}, default_plain="skipped stop_hook_active")
    srec = get_session_record(pcfg, sid) if sid else None
    if not srec or not srec.get("enabled"):
        return emit(args, {"skipped": "session_not_enabled"}, default_plain="skipped session_not_enabled")
    role = srec.get("role")
    if not role or role not in pcfg.get("enabled_roles", []):
        return emit(args, {"skipped": "role_not_enabled"}, default_plain="skipped role_not_enabled")
    rcfg = pcfg.get("roles", {}).get(role)
    if not isinstance(rcfg, dict):
        return emit(args, {"skipped": "role_missing"}, default_plain="skipped role_missing")
    if should_debounce(pcfg, hp, args.channel):
        return emit(args, {"skipped": "debounced"}, default_plain="skipped debounced")
    # If central-router mode and router is alive, skip local sync — router handles it
    comm_mode = pcfg.get("communication_mode", "local-poller")
    if comm_mode == "central-router" and check_router_alive():
        return emit(args, {"skipped": "central_router_active"}, default_plain="skipped central_router_active")
    touch_hook_check(pcfg, args.channel)
    sp = sync_messages(pcfg, acct, channel_override=args.channel)
    dp = maybe_deliver(pcfg, role, rcfg, srec, channel_override=args.channel)
    return emit(args, {"sync": sp, "delivery": dp, "session_id": sid, "role": role},
                default_plain=f"session={sid} synced={sp['synced']} delivered={dp.get('delivered', False)}")


def cmd_poll(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    comm_mode = pcfg.get("communication_mode", "local-poller")
    last_router_check = 0.0
    deadline = time.time() + args.timeout if args.timeout else None
    while True:
        # Router detection: every 60s, check if central router is alive
        if comm_mode == "central-router":
            now = time.time()
            if now - last_router_check >= 60:
                last_router_check = now
                if check_router_alive():
                    print("central_router_detected action=stopping_local_poller")
                    break
        try: cmd_hook_check(args)
        except SystemExit as exc: print(f"poll_error={exc or exc.__class__.__name__}")
        except Exception as exc: print(f"poll_error={exc.__class__.__name__}: {exc}")
        if deadline is not None and time.time() >= deadline: return 0
        time.sleep(args.interval)


def cmd_poller_start(args: argparse.Namespace) -> int:
    pp, pcfg = load_project_config(args.project_config)
    comm_mode = pcfg.get("communication_mode", "local-poller")
    if comm_mode == "central-router":
        if check_router_alive():
            p = {"started": False, "reason": "central_router_running",
                 "message": "Central router is running, local poller not needed"}
            return emit(args, p, default_plain="Central router is running, local poller not needed")
        print("WARNING: Central router not running, starting local poller as fallback")
    sid = resolve_session_id(args, pcfg)
    srec = get_session_record(pcfg, sid)
    if not srec or not srec.get("enabled"): raise SystemExit("Selected session is not enabled")
    p = start_poller_process(pp, pcfg, session_id=sid, interval=args.interval, channel=args.channel)
    plain = (f"poller_started pid={p['pid']} session={p['session_id']}" if p.get("started")
             else f"poller={p.get('reason')} pid={p.get('pid', '-')}")
    return emit(args, p, default_plain=plain)


def cmd_poller_status(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    p = poller_runtime_status(pcfg); rec = p.get("record")
    if not rec: return emit(args, p, default_plain="poller not configured")
    return emit(args, p, default_plain=f"poller running={p['running']} pid={rec.get('pid')} "
                f"session={rec.get('session_id')} interval={rec.get('interval')}")


def cmd_poller_stop(args: argparse.Namespace) -> int:
    _, pcfg = load_project_config(args.project_config)
    p = stop_poller_process(pcfg)
    return emit(args, p, default_plain=(f"poller_stopped pid={p.get('pid')}" if p.get("stopped")
                                         else f"poller_stop={p.get('reason')}"))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    jf = lambda t: t.add_argument("--json", action="store_true", help="Emit JSON output")
    p = argparse.ArgumentParser(description="Project-scoped Slack gateway for agents")
    jf(p)
    p.add_argument("--project-config", help="Path to .agent-comms/slack.json")
    p.add_argument("--accounts-config", help="Path to ~/.config/agent-slack/accounts.json")
    sub = p.add_subparsers(dest="command", required=True)

    # account test
    ap = sub.add_parser("account", help="Account operations"); jf(ap)
    asub = ap.add_subparsers(dest="account_command", required=True)
    at = asub.add_parser("test", help="Verify via auth.test"); jf(at)
    at.add_argument("--account", help="Override account name"); at.set_defaults(func=cmd_account_test)

    # config validate
    cp = sub.add_parser("config", help="Configuration operations"); jf(cp)
    csub = cp.add_subparsers(dest="config_command", required=True)
    cv = csub.add_parser("validate", help="Validate config"); jf(cv)
    cv.set_defaults(func=cmd_config_validate)

    # send
    s = sub.add_parser("send", help="Post a Slack message"); jf(s)
    s.add_argument("--role"); s.add_argument("--agent-name")
    s.add_argument("--target-channel", help="Override Slack channel ID")
    s.add_argument("--channel", help="Logical channel"); s.add_argument("--message")
    s.add_argument("--stdin", action="store_true"); s.add_argument("--raw", action="store_true")
    s.add_argument("--thread-ts", help="Thread ts for reply")
    s.add_argument("--dm", help="User ID for DM"); s.set_defaults(func=cmd_send)

    # send-file
    sf = sub.add_parser("send-file", help="Upload a file"); jf(sf)
    sf.add_argument("--role"); sf.add_argument("--file", required=True)
    sf.add_argument("--caption", default=""); sf.add_argument("--channel")
    sf.add_argument("--thread-ts"); sf.set_defaults(func=cmd_send_file)

    # sync
    sy = sub.add_parser("sync", help="Sync inbound messages"); jf(sy)
    sy.add_argument("--channel"); sy.set_defaults(func=cmd_sync)

    # latest
    lt = sub.add_parser("latest", help="Show latest local message"); jf(lt)
    lt.add_argument("--channel"); lt.add_argument("--direction", choices=["inbound", "outbound"])
    lt.set_defaults(func=cmd_latest)

    # history
    hi = sub.add_parser("history", help="Show local message history"); jf(hi)
    hi.add_argument("--channel"); hi.add_argument("--direction", choices=["inbound", "outbound"])
    hi.add_argument("--limit", type=int, default=10); hi.set_defaults(func=cmd_history)

    # unread
    ur = sub.add_parser("unread", help="Show unread inbound"); jf(ur)
    ur.add_argument("--channel"); ur.add_argument("--limit", type=int, default=10)
    ur.set_defaults(func=cmd_unread)

    # mark-read
    mr = sub.add_parser("mark-read", help="Mark inbound as read"); jf(mr)
    mr.add_argument("--channel"); mr.add_argument("--all", action="store_true")
    mr.add_argument("--count", type=int, help="Mark N oldest unread as read")
    mr.set_defaults(func=cmd_mark_read)

    # enable-session
    en = sub.add_parser("enable-session", help="Enable Slack handling for session"); jf(en)
    en.add_argument("--role"); en.add_argument("--session-id")
    en.add_argument("--tmux-session"); en.add_argument("--channel")
    en.add_argument("--use-latest-seen", action="store_true")
    en.add_argument("--start-poller", action="store_true")
    en.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    en.set_defaults(func=cmd_enable_session)

    # disable-session
    di = sub.add_parser("disable-session", help="Disable Slack handling"); jf(di)
    di.add_argument("--session-id"); di.add_argument("--use-latest-seen", action="store_true")
    di.add_argument("--stop-poller", action="store_true"); di.set_defaults(func=cmd_disable_session)

    # session-status
    ss = sub.add_parser("session-status", help="Show session state"); jf(ss)
    ss.add_argument("--session-id"); ss.add_argument("--use-latest-seen", action="store_true")
    ss.add_argument("--all", action="store_true"); ss.set_defaults(func=cmd_session_status)

    # hook-check
    hk = sub.add_parser("hook-check", help="Hook-triggered sync and delivery"); jf(hk)
    hk.add_argument("--channel"); hk.add_argument("--session-id")
    hk.add_argument("--use-latest-seen", action="store_true")
    hk.add_argument("--stdin-hook", action="store_true"); hk.set_defaults(func=cmd_hook_check)

    # poll
    po = sub.add_parser("poll", help="Continuous polling loop"); jf(po)
    po.add_argument("--channel"); po.add_argument("--session-id")
    po.add_argument("--use-latest-seen", action="store_true")
    po.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL)
    po.add_argument("--timeout", type=int); po.add_argument("--stdin-hook", action="store_true")
    po.set_defaults(func=cmd_poll)

    # poller (start/status/stop)
    pl = sub.add_parser("poller", help="Manage background poller"); jf(pl)
    plsub = pl.add_subparsers(dest="poller_command", required=True)
    ps = plsub.add_parser("start", help="Start background poller"); jf(ps)
    ps.add_argument("--channel"); ps.add_argument("--session-id")
    ps.add_argument("--use-latest-seen", action="store_true")
    ps.add_argument("--interval", type=int, default=DEFAULT_POLL_INTERVAL)
    ps.set_defaults(func=cmd_poller_start)
    pst = plsub.add_parser("status", help="Poller status"); jf(pst)
    pst.set_defaults(func=cmd_poller_status)
    psp = plsub.add_parser("stop", help="Stop poller"); jf(psp)
    psp.set_defaults(func=cmd_poller_stop)

    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
