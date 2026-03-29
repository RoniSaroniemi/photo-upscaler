#!/usr/bin/env python3
"""Central communication router daemon.

Polls Telegram and Slack APIs per bot account and routes inbound messages
to the correct project's tmux session based on route matching.

Usage:
    python3 tools/central_router.py --config <path> run
    python3 tools/central_router.py --config <path> start
    python3 tools/central_router.py --config <path> stop
    python3 tools/central_router.py --config <path> status
    python3 tools/central_router.py --config <path> validate
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# ---------------------------------------------------------------------------
# PidLock import — tools/ sits next to this file's parent
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.pid_lock import PidLock  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agent-telegram" / "projects"
SLACK_DATA_ROOT = Path.home() / ".local" / "share" / "agent-slack" / "projects"
SLACK_API_BASE = "https://slack.com/api"
SLACK_IGNORED_SUBTYPES = frozenset({
    "channel_join", "channel_leave", "channel_topic",
    "channel_purpose", "bot_message",
})
MAX_RECENT_EVENTS = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def expand(p: str) -> Path:
    """Expand ~ and return a resolved Path."""
    return Path(os.path.expanduser(p)).resolve()


def log(msg: str) -> None:
    ts = now_iso()
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Config loading & validation
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_config(cfg: dict) -> list[str]:
    """Return a list of error strings.  Empty list = valid."""
    errors: list[str] = []

    for key in ("router_pid_file", "status_file"):
        if key not in cfg or not isinstance(cfg[key], str):
            errors.append(f"Missing or invalid top-level key: {key}")

    transports = cfg.get("transports")
    if not isinstance(transports, dict):
        errors.append("Missing or invalid 'transports' dict")
        return errors

    tg = transports.get("telegram")
    if tg is not None:
        if not isinstance(tg, dict):
            errors.append("transports.telegram must be a dict")
            return errors
        if "accounts_config" not in tg:
            errors.append("transports.telegram.accounts_config is required")
        bots = tg.get("bots")
        if not isinstance(bots, list):
            errors.append("transports.telegram.bots must be a list")
            return errors
        for i, bot in enumerate(bots):
            prefix = f"transports.telegram.bots[{i}]"
            for bk in ("account", "poll_interval_seconds", "long_poll_timeout"):
                if bk not in bot:
                    errors.append(f"{prefix}.{bk} is required")
            routes = bot.get("routes")
            if not isinstance(routes, list) or len(routes) == 0:
                errors.append(f"{prefix}.routes must be a non-empty list")
                continue
            for j, route in enumerate(routes):
                rp = f"{prefix}.routes[{j}]"
                for rk in ("match", "project_id", "tmux_session", "state_dir", "channel", "inject_format"):
                    if rk not in route:
                        errors.append(f"{rp}.{rk} is required")
                match = route.get("match")
                if isinstance(match, dict):
                    if "chat_id" not in match:
                        errors.append(f"{rp}.match.chat_id is required")
                else:
                    errors.append(f"{rp}.match must be a dict")

    # Validate Slack transport
    sl = transports.get("slack")
    if sl is not None:
        if not isinstance(sl, dict):
            errors.append("transports.slack must be a dict")
            return errors
        if "accounts_config" not in sl:
            errors.append("transports.slack.accounts_config is required")
        bots = sl.get("bots")
        if not isinstance(bots, list):
            errors.append("transports.slack.bots must be a list")
            return errors
        for i, bot in enumerate(bots):
            prefix = f"transports.slack.bots[{i}]"
            for bk in ("account", "poll_interval_seconds"):
                if bk not in bot:
                    errors.append(f"{prefix}.{bk} is required")
            routes = bot.get("routes")
            if not isinstance(routes, list) or len(routes) == 0:
                errors.append(f"{prefix}.routes must be a non-empty list")
                continue
            for j, route in enumerate(routes):
                rp = f"{prefix}.routes[{j}]"
                for rk in ("match", "project_id", "tmux_session", "state_dir", "channel", "inject_format"):
                    if rk not in route:
                        errors.append(f"{rp}.{rk} is required")
                match = route.get("match")
                if not isinstance(match, dict):
                    errors.append(f"{rp}.match must be a dict")

    return errors


# ---------------------------------------------------------------------------
# Telegram helpers (replicated from agent_telegram.py — standalone daemon)
# ---------------------------------------------------------------------------

def telegram_message_timestamp_iso(message: dict) -> str:
    raw = message.get("date")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, timezone.utc).isoformat().replace("+00:00", "Z")
    return now_iso()


def normalize_text(message: dict) -> str:
    text = message.get("text") or message.get("caption")
    if text:
        return str(text)
    return "<non-text message>"


def normalize_sender(message: dict) -> str:
    sender = message.get("from") or {}
    return str(
        sender.get("username")
        or sender.get("first_name")
        or sender.get("id")
        or "unknown"
    )


def build_inbound_record(route: dict, message: dict, update_id: int) -> dict:
    chat = message.get("chat") or {}
    voice = message.get("voice")
    record: dict = {
        "direction": "inbound",
        "timestamp": telegram_message_timestamp_iso(message),
        "project_id": route["project_id"],
        "channel": route["channel"],
        "agent_name": None,
        "chat_id": str(chat.get("id")),
        "message_id": str(message.get("message_id")),
        "update_id": update_id,
        "sender_label": normalize_sender(message),
        "text": normalize_text(message),
        "read": False,
    }
    if isinstance(voice, dict):
        record["media_type"] = "voice"
        record["voice"] = {
            "file_id": voice.get("file_id"),
            "file_unique_id": voice.get("file_unique_id"),
            "duration_seconds": voice.get("duration"),
            "mime_type": voice.get("mime_type"),
            "file_size": voice.get("file_size"),
        }
        record["transcription"] = {
            "status": "pending",
            "text": None,
            "provider": "speak2",
            "engine": None,
            "language": None,
            "error": None,
            "last_attempt_at": None,
        }
    else:
        record["media_type"] = "text"
    return record


# ---------------------------------------------------------------------------
# State I/O (compatible with agent_telegram.py paths)
# ---------------------------------------------------------------------------

def channel_root(project_id: str, channel: str) -> Path:
    return DEFAULT_DATA_ROOT / project_id / channel


def history_path(project_id: str, channel: str) -> Path:
    return channel_root(project_id, channel) / "history.jsonl"


def state_path(project_id: str, channel: str) -> Path:
    return channel_root(project_id, channel) / "state.json"


def append_history(project_id: str, channel: str, record: dict) -> None:
    path = history_path(project_id, channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True))
        fh.write("\n")


def load_state(project_id: str, channel: str) -> dict:
    path = state_path(project_id, channel)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(project_id: str, channel: str, state: dict) -> None:
    path = state_path(project_id, channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Slack State I/O (compatible with agent_slack.py paths)
# ---------------------------------------------------------------------------

def slack_channel_root(project_id: str, channel: str) -> Path:
    return SLACK_DATA_ROOT / project_id / channel


def slack_history_path(project_id: str, channel: str) -> Path:
    return slack_channel_root(project_id, channel) / "history.jsonl"


def slack_state_path(project_id: str, channel: str) -> Path:
    return slack_channel_root(project_id, channel) / "state.json"


def slack_append_history(project_id: str, channel: str, record: dict) -> None:
    path = slack_history_path(project_id, channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True))
        fh.write("\n")


def slack_load_state(project_id: str, channel: str) -> dict:
    path = slack_state_path(project_id, channel)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def slack_save_state(project_id: str, channel: str, state: dict) -> None:
    path = slack_state_path(project_id, channel)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def slack_message_key(rec: dict) -> str:
    return f"{rec.get('direction')}:{rec.get('ts')}"


# ---------------------------------------------------------------------------
# Slack API helpers
# ---------------------------------------------------------------------------

def slack_api_request(token: str, method: str, payload: dict | None = None,
                      *, min_interval_ms: int = 1100, timeout: int = 30,
                      _state: dict = {"last_call": 0.0}) -> dict:
    """Make a Slack Web API call with rate-limit awareness.

    Uses a mutable default dict to track last call time across invocations.
    """
    elapsed_ms = (time.time() - _state["last_call"]) * 1000
    if elapsed_ms < min_interval_ms:
        time.sleep((min_interval_ms - elapsed_ms) / 1000)

    url = f"{SLACK_API_BASE}/{method}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = json.dumps(payload or {}).encode("utf-8")

    retry_cap = 30
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        _state["last_call"] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                ra = exc.headers.get("Retry-After")
                wait = min(int(ra) if ra else 1, retry_cap)
                if attempt < 3:
                    time.sleep(wait)
                    continue
            raise
        except (urllib.error.URLError, OSError):
            raise

        if not isinstance(result, dict):
            raise RuntimeError(f"Slack API returned non-object: {result!r}")
        if not result.get("ok"):
            err = result.get("error", "unknown_error")
            if err == "ratelimited" and attempt < 3:
                time.sleep(1)
                continue
            raise RuntimeError(f"Slack API error: {err}")
        return result

    raise RuntimeError("Slack API request failed after retries")


def slack_ts_to_iso(msg: dict) -> str:
    """Convert a Slack message ts to ISO timestamp (matching agent_slack.py)."""
    raw = msg.get("ts")
    if isinstance(raw, str):
        try:
            return datetime.fromtimestamp(float(raw), timezone.utc).isoformat().replace("+00:00", "Z")
        except (ValueError, OverflowError):
            pass
    return now_iso()


def build_slack_inbound_record(route: dict, slack_channel: str, msg: dict) -> dict:
    """Build an inbound record matching agent_slack.py format exactly."""
    ts = msg.get("ts", "")
    thr = msg.get("thread_ts")
    return {
        "direction": "inbound",
        "timestamp": slack_ts_to_iso(msg),
        "ts": ts,
        "project_id": route["project_id"],
        "channel": route["channel"],
        "agent_name": None,
        "slack_channel": slack_channel,
        "message_id": ts,
        "thread_ts": thr if thr and thr != ts else None,
        "sender_id": msg.get("user", "unknown"),
        "sender_label": msg.get("user", "unknown"),
        "text": msg.get("text") or "<non-text message>",
        "read": False,
        "media_type": "text",
    }


def slack_normalize_sender(msg: dict) -> str:
    """Return a sender label for tmux injection."""
    return msg.get("user") or "unknown"


# ---------------------------------------------------------------------------
# Status file
# ---------------------------------------------------------------------------

def write_status(status_path: Path, status: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=status_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(status, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, status_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Router core
# ---------------------------------------------------------------------------

class Router:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pid_path = expand(cfg["router_pid_file"])
        self.status_path = expand(cfg["status_file"])
        self.started_at = now_iso()
        self._shutdown = False

        # Per-bot runtime state: keyed by "{transport}:{account}"
        self.bot_state: dict[str, dict] = {}
        self.recent_events: list[dict] = []

        # Slack-specific state
        self.slack_bot_state: dict[str, dict] = {}
        self.slack_dm_cache: dict[str, dict[str, str]] = {}  # account -> {user_id: dm_channel_id}
        self.slack_dm_cache_ts: dict[str, float] = {}  # account -> last refresh monotonic time

        self._init_bot_state()
        self._init_slack_state()

    # -- initialisation ------------------------------------------------------

    def _init_bot_state(self) -> None:
        tg = self.cfg.get("transports", {}).get("telegram")
        if not tg:
            return

        # Load bot tokens from accounts_config
        accounts_path = expand(tg["accounts_config"])
        accounts: dict = {}
        if accounts_path.exists():
            try:
                with accounts_path.open("r", encoding="utf-8") as fh:
                    accounts = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                log(f"Failed to load accounts config {accounts_path}: {exc}")

        for bot in tg.get("bots", []):
            account = bot["account"]
            # Resolve token — accounts.json uses {"accounts": {"name": {"bot_token": "..."}}}
            acct_data = accounts.get("accounts", accounts).get(account) or {}
            token = acct_data.get("bot_token") or acct_data.get("token")

            if not token:
                log(f"No token found for account {account!r} in {accounts_path}")

            self.bot_state[account] = {
                "token": token,
                "last_poll_time": 0.0,
                "last_poll_iso": None,
                "poll_interval": bot["poll_interval_seconds"],
                "long_poll_timeout": bot["long_poll_timeout"],
                "routes": bot["routes"],
                "status": "error" if not token else "idle",
                "messages_delivered_today": 0,
                "errors_today": 0,
                "routes_active": len(bot["routes"]),
            }

        # Per-bot next_update_id tracking (in-memory, seeded from state files)
        self.next_update_ids: dict[str, int] = {}
        for account, bs in self.bot_state.items():
            # Seed from the first route's state.json if it has a next_update_id
            for route in bs["routes"]:
                st = load_state(route["project_id"], route["channel"])
                nuid = st.get("next_update_id")
                if isinstance(nuid, int) and nuid > 0:
                    self.next_update_ids[account] = nuid
                    break
            self.next_update_ids.setdefault(account, 0)

    # -- signal handling -----------------------------------------------------

    def _handle_signal(self, signum: int, frame: object) -> None:
        sig_name = signal.Signals(signum).name
        log(f"Received {sig_name} — shutting down")
        self._shutdown = True

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    # -- status output -------------------------------------------------------

    def build_status(self) -> dict:
        started_dt = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        uptime = (now_dt - started_dt).total_seconds() / 60.0

        tg_bots_status: dict[str, dict] = {}
        for account, bs in self.bot_state.items():
            tg_bots_status[account] = {
                "status": bs["status"],
                "last_poll": bs["last_poll_iso"],
                "messages_delivered_today": bs["messages_delivered_today"],
                "routes_active": bs["routes_active"],
                "errors_today": bs["errors_today"],
            }

        slack_bots_status: dict[str, dict] = {}
        for account, bs in self.slack_bot_state.items():
            slack_bots_status[account] = {
                "status": bs["status"],
                "last_poll": bs["last_poll_iso"],
                "messages_delivered_today": bs["messages_delivered_today"],
                "routes_active": bs["routes_active"],
                "errors_today": bs["errors_today"],
            }

        transports: dict = {}
        if tg_bots_status:
            transports["telegram"] = {"bots": tg_bots_status}
        if slack_bots_status:
            transports["slack"] = {"bots": slack_bots_status}

        return {
            "router_pid": os.getpid(),
            "started_at": self.started_at,
            "uptime_minutes": round(uptime, 2),
            "last_cycle": now_iso(),
            "transports": transports,
            "recent_events": list(self.recent_events[-MAX_RECENT_EVENTS:]),
        }

    def add_event(self, transport: str, bot: str, event: str, route: str = "") -> None:
        entry = {
            "time": now_iso(),
            "transport": transport,
            "bot": bot,
            "event": event,
            "route": route,
        }
        self.recent_events.append(entry)
        if len(self.recent_events) > MAX_RECENT_EVENTS:
            self.recent_events = self.recent_events[-MAX_RECENT_EVENTS:]

    # -- Telegram transport --------------------------------------------------

    def poll_bot(self, account: str) -> None:
        bs = self.bot_state[account]
        token = bs.get("token")
        if not token:
            bs["status"] = "error"
            return

        offset = self.next_update_ids.get(account, 0)
        timeout = bs["long_poll_timeout"]
        url = (
            f"https://api.telegram.org/bot{token}/getUpdates"
            f"?offset={offset}&timeout={timeout}"
            f"&allowed_updates=%5B%22message%22%5D"
        )

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            log(f"Poll error for bot {account!r}: {exc}")
            bs["errors_today"] += 1
            bs["status"] = "error"
            self.add_event("telegram", account, "poll_error")
            return
        except json.JSONDecodeError as exc:
            log(f"Invalid JSON from Telegram for bot {account!r}: {exc}")
            bs["errors_today"] += 1
            bs["status"] = "error"
            return

        bs["last_poll_iso"] = now_iso()
        bs["status"] = "healthy"

        if not body.get("ok"):
            log(f"Telegram API returned ok=false for bot {account!r}: {body}")
            bs["errors_today"] += 1
            self.add_event("telegram", account, "api_error")
            return

        updates = body.get("result") or []
        if not updates:
            return

        highest_id = offset
        # Track which project/channel combos need state.json updated
        touched_routes: set[tuple[str, str]] = set()

        for update in updates:
            uid = update.get("update_id", 0)
            if uid >= highest_id:
                highest_id = uid

            message = update.get("message")
            if not message:
                continue

            self.match_and_deliver(account, update, touched_routes)

        # Advance next_update_id past the highest seen
        self.next_update_ids[account] = highest_id + 1

        # Persist next_update_id to each touched route's state.json
        for project_id, channel in touched_routes:
            try:
                st = load_state(project_id, channel)
                st["next_update_id"] = self.next_update_ids[account]
                save_state(project_id, channel, st)
            except Exception as exc:
                log(f"Failed to save state for {project_id}/{channel}: {exc}")

    def match_route(self, account: str, message: dict) -> dict | None:
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        bs = self.bot_state[account]
        for route in bs["routes"]:
            match = route.get("match", {})
            if match.get("chat_id") == chat_id:
                return route
        return None

    def match_and_deliver(self, account: str, update: dict, touched_routes: set[tuple[str, str]]) -> None:
        message = update.get("message")
        if not message:
            return

        route = self.match_route(account, message)
        if route is None:
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", ""))
            log(f"No route for chat_id {chat_id} on bot {account!r}")
            return

        update_id = update.get("update_id", 0)
        record = build_inbound_record(route, message, update_id)

        project_id = route["project_id"]
        channel = route["channel"]

        # Write to history
        try:
            append_history(project_id, channel, record)
        except Exception as exc:
            log(f"Failed to append history for {project_id}/{channel}: {exc}")

        touched_routes.add((project_id, channel))

        # Inject into tmux (best-effort — still write state even if injection fails)
        try:
            self.inject_tmux(route, message)
        except Exception as exc:
            log(f"tmux injection failed for {project_id}/{route['tmux_session']}: {exc}")

        bs = self.bot_state[account]
        bs["messages_delivered_today"] += 1
        self.add_event(
            "telegram", account, "message_delivered",
            f"{project_id}/{route['tmux_session']}",
        )
        log(f"Delivered message to {project_id}/{channel} via {route['tmux_session']}")

    def inject_tmux(self, route: dict, message: dict) -> bool:
        text = route["inject_format"].format(
            project_id=route["project_id"],
            channel=route["channel"],
            sender=normalize_sender(message),
            text=normalize_text(message),
        )

        tmux_cmd: list[str] = ["tmux"]
        if route.get("tmux_server"):
            tmux_cmd += ["-L", route["tmux_server"]]

        # Check session exists
        result = subprocess.run(
            tmux_cmd + ["has-session", "-t", route["tmux_session"]],
            capture_output=True,
        )
        if result.returncode != 0:
            log(f"tmux session {route['tmux_session']!r} does not exist — skipping injection")
            return False

        buf_name = f"router-{uuid4().hex[:8]}"

        # load-buffer from stdin
        result = subprocess.run(
            tmux_cmd + ["load-buffer", "-b", buf_name, "-"],
            input=text.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode != 0:
            log(f"tmux load-buffer failed: {result.stderr.decode(errors='replace')}")
            return False

        # paste-buffer with bracketed paste
        subprocess.run(
            tmux_cmd + ["paste-buffer", "-p", "-d", "-b", buf_name, "-t", route["tmux_session"]],
            capture_output=True,
        )

        time.sleep(0.3)

        # send Enter
        subprocess.run(
            tmux_cmd + ["send-keys", "-t", route["tmux_session"], "Enter"],
            capture_output=True,
        )

        return True

    # -- Slack transport -----------------------------------------------------

    def _init_slack_state(self) -> None:
        sl = self.cfg.get("transports", {}).get("slack")
        if not sl:
            return

        accounts_path = expand(sl["accounts_config"])
        accounts: dict = {}
        if accounts_path.exists():
            try:
                with accounts_path.open("r", encoding="utf-8") as fh:
                    accounts = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                log(f"Failed to load Slack accounts config {accounts_path}: {exc}")

        for bot in sl.get("bots", []):
            account = bot["account"]
            acct_data = accounts.get("accounts", accounts).get(account) or {}
            token = acct_data.get("bot_token") or acct_data.get("token")
            bot_user_id = acct_data.get("bot_user_id") or ""

            if not token:
                log(f"No Slack token found for account {account!r} in {accounts_path}")

            min_interval = bot.get("min_interval_ms", 1100)

            # Collect all unique channels to poll (channel routes) and DM user_ids
            channels_to_poll: list[str] = []
            dm_user_ids: list[str] = []
            seen_channels: set[str] = set()

            for route in bot.get("routes", []):
                match = route.get("match", {})
                ch = match.get("channel")
                if ch and ch not in seen_channels:
                    channels_to_poll.append(ch)
                    seen_channels.add(ch)
                elif match.get("type") in ("dm", "any"):
                    uid = match.get("user_id")
                    if uid and uid not in dm_user_ids:
                        dm_user_ids.append(uid)

            self.slack_bot_state[account] = {
                "token": token,
                "bot_user_id": bot_user_id,
                "last_poll_time": 0.0,
                "last_poll_iso": None,
                "poll_interval": bot["poll_interval_seconds"],
                "min_interval_ms": min_interval,
                "routes": bot["routes"],
                "channels_to_poll": channels_to_poll,
                "dm_user_ids": dm_user_ids,
                "status": "error" if not token else "idle",
                "messages_delivered_today": 0,
                "errors_today": 0,
                "routes_active": len(bot["routes"]),
            }

            # Initialize DM cache
            self.slack_dm_cache[account] = {}
            self.slack_dm_cache_ts[account] = 0.0

    def refresh_slack_dm_cache(self, account: str) -> None:
        """Discover DM channel IDs via conversations.list (types=im)."""
        bs = self.slack_bot_state[account]
        token = bs.get("token")
        if not token:
            return

        now = time.monotonic()
        # Only refresh every 5 minutes
        if now - self.slack_dm_cache_ts.get(account, 0.0) < 300:
            return

        try:
            params: dict = {"types": "im", "limit": 200}
            all_channels: list[dict] = []
            has_more = True
            while has_more:
                resp = slack_api_request(token, "conversations.list", params,
                                         min_interval_ms=bs["min_interval_ms"])
                all_channels.extend(resp.get("channels", []))
                nc = (resp.get("response_metadata") or {}).get("next_cursor")
                if nc:
                    params["cursor"] = nc
                else:
                    has_more = False

            dm_map: dict[str, str] = {}
            for ch in all_channels:
                user = ch.get("user")
                ch_id = ch.get("id")
                if user and ch_id:
                    dm_map[user] = ch_id

            self.slack_dm_cache[account] = dm_map
            self.slack_dm_cache_ts[account] = now
            log(f"Slack DM cache refreshed for {account!r}: {len(dm_map)} DM channels")
        except Exception as exc:
            log(f"Failed to refresh Slack DM cache for {account!r}: {exc}")
            bs["errors_today"] += 1

    def match_slack_route(self, account: str, slack_channel: str, msg: dict) -> dict | None:
        """Match a Slack message to a route. First match wins.

        Match types:
        - {"channel": "CXXX"} — specific channel
        - {"type": "dm", "user_id": "UXXX"} — DM from specific user
        - {"type": "dm"} — any DM (wildcard)
        - {"type": "any"} — catch-all
        """
        bs = self.slack_bot_state[account]
        user_id = msg.get("user", "")
        is_dm = self._is_dm_channel(account, slack_channel)

        for route in bs["routes"]:
            match = route.get("match", {})

            # Channel match
            if "channel" in match:
                if match["channel"] == slack_channel:
                    return route
                continue

            match_type = match.get("type")

            # DM + user_id match
            if match_type == "dm" and "user_id" in match:
                if is_dm and match["user_id"] == user_id:
                    return route
                continue

            # DM wildcard
            if match_type == "dm" and "user_id" not in match:
                if is_dm:
                    return route
                continue

            # Catch-all
            if match_type == "any":
                return route

        return None

    def _is_dm_channel(self, account: str, slack_channel: str) -> bool:
        """Check if a Slack channel ID is a DM channel."""
        dm_cache = self.slack_dm_cache.get(account, {})
        return slack_channel in dm_cache.values()

    def _get_dm_channels_to_poll(self, account: str) -> list[str]:
        """Get the DM channel IDs that need polling based on routes."""
        bs = self.slack_bot_state[account]
        dm_cache = self.slack_dm_cache.get(account, {})
        dm_channels: list[str] = []
        seen: set[str] = set()

        has_dm_wildcard = False
        specific_dm_users: list[str] = []

        for route in bs["routes"]:
            match = route.get("match", {})
            match_type = match.get("type")
            if match_type == "dm":
                uid = match.get("user_id")
                if uid:
                    specific_dm_users.append(uid)
                else:
                    has_dm_wildcard = True
            elif match_type == "any":
                has_dm_wildcard = True

        if has_dm_wildcard:
            # Poll all known DM channels
            for uid, ch_id in dm_cache.items():
                if ch_id not in seen:
                    dm_channels.append(ch_id)
                    seen.add(ch_id)
        else:
            # Poll only specific user DMs
            for uid in specific_dm_users:
                ch_id = dm_cache.get(uid)
                if ch_id and ch_id not in seen:
                    dm_channels.append(ch_id)
                    seen.add(ch_id)

        return dm_channels

    def poll_slack_bot(self, account: str) -> None:
        """Poll all channels for a Slack bot account."""
        bs = self.slack_bot_state[account]
        token = bs.get("token")
        if not token:
            bs["status"] = "error"
            return

        min_interval_ms = bs["min_interval_ms"]
        bot_user_id = bs.get("bot_user_id", "")

        # Refresh DM cache if needed
        self.refresh_slack_dm_cache(account)

        # Build list of channels to poll: explicit channels + DM channels
        channels_to_poll: list[str] = list(bs["channels_to_poll"])
        dm_channels = self._get_dm_channels_to_poll(account)
        channels_to_poll.extend(dm_channels)

        if not channels_to_poll:
            bs["status"] = "healthy"
            bs["last_poll_iso"] = now_iso()
            return

        # Track which project/channel combos need state updated
        touched_routes: set[tuple[str, str]] = set()

        # Poll each Slack channel sequentially (rate limiting)
        for slack_ch in channels_to_poll:
            if self._shutdown:
                break
            try:
                self._poll_slack_channel(account, slack_ch, bot_user_id,
                                          min_interval_ms, touched_routes)
            except Exception as exc:
                log(f"Error polling Slack channel {slack_ch} for bot {account!r}: {exc}")
                bs["errors_today"] += 1
                self.add_event("slack", account, "poll_error", slack_ch)

        bs["last_poll_iso"] = now_iso()
        bs["status"] = "healthy"

        # Persist state for all touched routes
        for project_id, channel in touched_routes:
            try:
                st = slack_load_state(project_id, channel)
                st["last_sync_at"] = now_iso()
                slack_save_state(project_id, channel, st)
            except Exception as exc:
                log(f"Failed to save Slack state for {project_id}/{channel}: {exc}")

    def _poll_slack_channel(self, account: str, slack_ch: str, bot_user_id: str,
                             min_interval_ms: int,
                             touched_routes: set[tuple[str, str]]) -> None:
        """Poll a single Slack channel using conversations.history."""
        bs = self.slack_bot_state[account]
        token = bs["token"]

        # Find the last_seen_ts for this channel from state files.
        # Multiple routes may reference the same Slack channel, so check all.
        last_seen_ts = "0"
        for route in bs["routes"]:
            match = route.get("match", {})
            if match.get("channel") == slack_ch or self._route_covers_channel(account, route, slack_ch):
                st = slack_load_state(route["project_id"], route["channel"])
                rts = st.get("last_seen_ts") or "0"
                if rts > last_seen_ts:
                    last_seen_ts = rts

        # Fetch messages with cursor pagination
        params: dict = {"channel": slack_ch, "limit": 100}
        if last_seen_ts != "0":
            params["oldest"] = last_seen_ts

        all_msgs: list[dict] = []
        has_more = True
        while has_more:
            resp = slack_api_request(token, "conversations.history", params,
                                     min_interval_ms=min_interval_ms)
            all_msgs.extend(resp.get("messages", []))
            nc = (resp.get("response_metadata") or {}).get("next_cursor")
            if nc:
                params["cursor"] = nc
            else:
                has_more = False

        # Slack returns newest-first — reverse to chronological
        all_msgs.reverse()

        # Process each message
        newest_ts = last_seen_ts
        for msg in all_msgs:
            mts = msg.get("ts", "")

            # Skip the exact last_seen_ts message (already processed)
            if last_seen_ts != "0" and mts == last_seen_ts:
                continue

            # Bot self-message filtering
            if bot_user_id and msg.get("user") == bot_user_id:
                continue

            # Subtype filtering
            if msg.get("subtype") in SLACK_IGNORED_SUBTYPES:
                continue

            # Route matching
            route = self.match_slack_route(account, slack_ch, msg)
            if route is None:
                continue

            # Build record (matching agent_slack.py format)
            record = build_slack_inbound_record(route, slack_ch, msg)

            project_id = route["project_id"]
            channel = route["channel"]

            # Dedup: check if this ts is already in history
            existing_state = slack_load_state(project_id, channel)
            existing_last = existing_state.get("last_seen_ts") or "0"
            if mts <= existing_last and mts != "0":
                continue

            # Write to history
            try:
                slack_append_history(project_id, channel, record)
            except Exception as exc:
                log(f"Failed to append Slack history for {project_id}/{channel}: {exc}")
                continue

            touched_routes.add((project_id, channel))

            # Inject into tmux
            try:
                self.slack_inject_tmux(route, msg)
            except Exception as exc:
                log(f"Slack tmux injection failed for {project_id}/{route['tmux_session']}: {exc}")

            bs["messages_delivered_today"] += 1
            self.add_event(
                "slack", account, "message_delivered",
                f"{project_id}/{route['tmux_session']}",
            )
            log(f"Delivered Slack message to {project_id}/{channel} via {route['tmux_session']}")

            if mts > newest_ts:
                newest_ts = mts

        # Update last_seen_ts for all routes that match this Slack channel
        if newest_ts > last_seen_ts:
            for route in bs["routes"]:
                match = route.get("match", {})
                if match.get("channel") == slack_ch or self._route_covers_channel(account, route, slack_ch):
                    pid = route["project_id"]
                    ch = route["channel"]
                    st = slack_load_state(pid, ch)
                    st["last_seen_ts"] = newest_ts
                    touched_routes.add((pid, ch))
                    try:
                        slack_save_state(pid, ch, st)
                    except Exception as exc:
                        log(f"Failed to save Slack state for {pid}/{ch}: {exc}")

    def _route_covers_channel(self, account: str, route: dict, slack_ch: str) -> bool:
        """Check if a DM/catch-all route covers a given Slack channel."""
        match = route.get("match", {})
        match_type = match.get("type")
        if match_type == "any":
            return True
        if match_type == "dm":
            uid = match.get("user_id")
            dm_cache = self.slack_dm_cache.get(account, {})
            if uid:
                return dm_cache.get(uid) == slack_ch
            # DM wildcard — covers any DM channel
            return slack_ch in dm_cache.values()
        return False

    def slack_inject_tmux(self, route: dict, msg: dict) -> bool:
        """Inject a Slack message into a tmux session."""
        text = route["inject_format"].format(
            project_id=route["project_id"],
            channel=route["channel"],
            sender=slack_normalize_sender(msg),
            text=msg.get("text") or "<non-text message>",
        )

        tmux_cmd: list[str] = ["tmux"]
        if route.get("tmux_server"):
            tmux_cmd += ["-L", route["tmux_server"]]

        # Check session exists
        result = subprocess.run(
            tmux_cmd + ["has-session", "-t", route["tmux_session"]],
            capture_output=True,
        )
        if result.returncode != 0:
            log(f"tmux session {route['tmux_session']!r} does not exist — skipping Slack injection")
            return False

        buf_name = f"router-{uuid4().hex[:8]}"

        result = subprocess.run(
            tmux_cmd + ["load-buffer", "-b", buf_name, "-"],
            input=text.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode != 0:
            log(f"tmux load-buffer failed: {result.stderr.decode(errors='replace')}")
            return False

        subprocess.run(
            tmux_cmd + ["paste-buffer", "-p", "-d", "-b", buf_name, "-t", route["tmux_session"]],
            capture_output=True,
        )

        time.sleep(0.3)

        subprocess.run(
            tmux_cmd + ["send-keys", "-t", route["tmux_session"], "Enter"],
            capture_output=True,
        )

        return True

    # -- main loop -----------------------------------------------------------

    def run(self) -> None:
        log(f"Router started (PID {os.getpid()})")
        self.install_signal_handlers()

        while not self._shutdown:
            now = time.monotonic()

            # Poll Telegram bots
            for account, bs in self.bot_state.items():
                elapsed = now - bs["last_poll_time"]
                if elapsed >= bs["poll_interval"]:
                    self.poll_bot(account)
                    bs["last_poll_time"] = time.monotonic()

            # Poll Slack bots
            for account, bs in self.slack_bot_state.items():
                elapsed = now - bs["last_poll_time"]
                if elapsed >= bs["poll_interval"]:
                    self.poll_slack_bot(account)
                    bs["last_poll_time"] = time.monotonic()

            try:
                write_status(self.status_path, self.build_status())
            except Exception as exc:
                log(f"Failed to write status: {exc}")

            time.sleep(1)

        log("Router stopped")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_validate(cfg: dict) -> int:
    errors = validate_config(cfg)
    if errors:
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        return 1
    print("Config OK")
    return 0


def cmd_run(cfg: dict) -> int:
    errors = validate_config(cfg)
    if errors:
        print("Config validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    pid_path = expand(cfg["router_pid_file"])
    lock = PidLock(str(pid_path))
    if not lock.acquire():
        print(f"Another router instance is running (lock: {pid_path})", file=sys.stderr)
        return 1

    try:
        router = Router(cfg)
        router.run()
    finally:
        lock.release()

    return 0


def cmd_start(cfg: dict) -> int:
    pid_path = expand(cfg["router_pid_file"])
    if PidLock.is_locked(str(pid_path)):
        print(f"Router already running (lock: {pid_path})", file=sys.stderr)
        return 1

    config_path_str = sys.argv[sys.argv.index("--config") + 1]
    proc = subprocess.Popen(
        [sys.executable, __file__, "--config", config_path_str, "run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Give the child a moment to acquire the lock
    time.sleep(0.5)
    if proc.poll() is not None:
        print("Router failed to start", file=sys.stderr)
        return 1

    print(f"Router started in background (PID {proc.pid})")
    return 0


def cmd_stop(cfg: dict) -> int:
    pid_path = expand(cfg["router_pid_file"])
    if not pid_path.exists():
        print("No PID file found — router is not running")
        return 0

    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError) as exc:
        print(f"Cannot read PID file: {exc}", file=sys.stderr)
        return 1

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        print(f"Process {pid} is not running (stale PID file)")
        try:
            pid_path.unlink()
        except OSError:
            pass
        return 0
    except PermissionError:
        pass

    print(f"Sending SIGTERM to PID {pid}")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        print(f"Failed to send signal: {exc}", file=sys.stderr)
        return 1

    # Wait up to 5 seconds for shutdown
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print("Router stopped")
            return 0
        time.sleep(0.1)

    print("Router did not stop within 5 seconds", file=sys.stderr)
    return 1


def cmd_status(cfg: dict) -> int:
    status_path = expand(cfg["status_file"])
    if not status_path.exists():
        print("No status file found — router may not be running")
        return 1

    try:
        with status_path.open("r", encoding="utf-8") as fh:
            status = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Cannot read status file: {exc}", file=sys.stderr)
        return 1

    pid = status.get("router_pid")
    alive = False
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            pass

    state = "running" if alive else "NOT running (stale status)"
    print(f"Router PID {pid} — {state}")
    print(f"  Started:  {status.get('started_at')}")
    print(f"  Uptime:   {status.get('uptime_minutes')} minutes")
    print(f"  Last cycle: {status.get('last_cycle')}")

    transports = status.get("transports", {})

    tg = transports.get("telegram", {})
    tg_bots = tg.get("bots", {})
    if tg_bots:
        print("  Telegram bots:")
        for name, info in tg_bots.items():
            print(f"    {name}: {info.get('status', '?')}"
                  f"  polls={info.get('last_poll', 'never')}"
                  f"  delivered={info.get('messages_delivered_today', 0)}"
                  f"  errors={info.get('errors_today', 0)}"
                  f"  routes={info.get('routes_active', 0)}")

    sl = transports.get("slack", {})
    sl_bots = sl.get("bots", {})
    if sl_bots:
        print("  Slack bots:")
        for name, info in sl_bots.items():
            print(f"    {name}: {info.get('status', '?')}"
                  f"  polls={info.get('last_poll', 'never')}"
                  f"  delivered={info.get('messages_delivered_today', 0)}"
                  f"  errors={info.get('errors_today', 0)}"
                  f"  routes={info.get('routes_active', 0)}")

    events = status.get("recent_events", [])
    if events:
        print(f"  Recent events: {len(events)}")
        for ev in events[-5:]:
            print(f"    [{ev.get('time')}] {ev.get('event')} bot={ev.get('bot')} route={ev.get('route')}")

    return 0


# ---------------------------------------------------------------------------
# Argument parsing & main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Central communication router daemon",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to router.json config file",
    )
    parser.add_argument(
        "command",
        choices=["run", "start", "stop", "status", "validate"],
        help="Command to execute",
    )
    args = parser.parse_args()

    config_path = expand(args.config)
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        cfg = load_config(config_path)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Failed to load config: {exc}", file=sys.stderr)
        return 1

    commands = {
        "run": cmd_run,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "validate": cmd_validate,
    }
    return commands[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
