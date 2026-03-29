#!/usr/bin/env python3
"""
Project-scoped Telegram gateway for Claude/Codex agents.

Secrets live outside the repo in:
  ~/.config/agent-telegram/accounts.json

Project config lives in:
  .agent-comms/telegram.json
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse

try:
    from tools.pid_lock import _pid_alive
except ImportError:
    import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
    from pid_lock import _pid_alive
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_CONFIG = Path(".agent-comms/telegram.json")
DEFAULT_ACCOUNT_CONFIG = Path.home() / ".config" / "agent-telegram" / "accounts.json"
DEFAULT_DATA_ROOT = Path.home() / ".local" / "share" / "agent-telegram" / "projects"
RECENT_SESSION_SECONDS = 15 * 60
DEFAULT_SPEAK2_BASE_URL = "http://127.0.0.1:8768"
DEFAULT_SPEAK2_SESSION_TOKEN = "speak2-local-dev-token"
DEFAULT_KOKORO_BASE_URL = "http://127.0.0.1:8770"
DEFAULT_KOKORO_SESSION_TOKEN = "kokoro-local-dev-token"
DEFAULT_KOKORO_VOICE = "af_heart"
DEFAULT_KOKORO_SPEED = 1.25
DEFAULT_KOKORO_LANGUAGE = "en-us"
DEFAULT_FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"
JSON_DEFAULT_MISSING = object()

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
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if default_plain is not None:
        print(default_plain)
        return 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}={value}")
        return 0
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                print(json.dumps(item, ensure_ascii=True))
            else:
                print(item)
        return 0
    print(payload)
    return 0


def load_json_file(path: Path, *, default: Any = JSON_DEFAULT_MISSING) -> Any:
    if not path.exists():
        if default is not JSON_DEFAULT_MISSING:
            return default
        raise SystemExit(f"Missing required file: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        if default is not JSON_DEFAULT_MISSING:
            return default
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def ensure_account_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f"{path} must be permission 0600 or stricter")


def resolve_project_config(path_arg: str | None) -> Path:
    return Path(path_arg).expanduser() if path_arg else DEFAULT_PROJECT_CONFIG


def load_project_config(path_arg: str | None) -> tuple[Path, dict[str, Any]]:
    path = resolve_project_config(path_arg)
    if not path.exists():
        example = path.with_suffix('.json.example') if path.suffix == '.json' else Path(str(path) + '.example')
        if example.exists():
            raise SystemExit(
                f'Config file not found: {path}\n'
                f'An example config exists at: {example}\n'
                f'To get started:\n'
                f'  cp {example} {path}\n'
                f'Then edit {path} and replace the placeholder values.'
            )
        raise SystemExit(f'Missing required config file: {path}')
    config = load_json_file(path)
    if not isinstance(config, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    config.setdefault("channel", "main")
    config.setdefault("enabled_roles", ["CPO"])
    config.setdefault("roles", {})
    config.setdefault("hook_debounce_seconds", 30)
    voice = config.setdefault("voice_transcription", {})
    if isinstance(voice, dict):
        voice.setdefault("enabled", True)
        voice.setdefault("base_url", DEFAULT_SPEAK2_BASE_URL)
        voice.setdefault("session_token", DEFAULT_SPEAK2_SESSION_TOKEN)
        voice.setdefault("language", "en")
        voice.setdefault("ffmpeg_path", DEFAULT_FFMPEG_PATH)
    synthesis = config.setdefault("voice_synthesis", {})
    if isinstance(synthesis, dict):
        synthesis.setdefault("enabled", True)
        synthesis.setdefault("base_url", DEFAULT_KOKORO_BASE_URL)
        synthesis.setdefault("session_token", DEFAULT_KOKORO_SESSION_TOKEN)
        synthesis.setdefault("default_voice", DEFAULT_KOKORO_VOICE)
        synthesis.setdefault("default_speed", DEFAULT_KOKORO_SPEED)
        synthesis.setdefault("language", DEFAULT_KOKORO_LANGUAGE)
        synthesis.setdefault("ffmpeg_path", DEFAULT_FFMPEG_PATH)
    global _tmux_server
    _tmux_server = config.get("tmux_server", "") or ""
    return path, config


def load_accounts(path_arg: str | None = None) -> tuple[Path, dict[str, Any]]:
    path = Path(path_arg).expanduser() if path_arg else DEFAULT_ACCOUNT_CONFIG
    accounts = load_json_file(path)
    if not isinstance(accounts, dict) or not isinstance(accounts.get("accounts"), dict):
        raise SystemExit(f"{path} must contain an accounts object")
    ensure_account_permissions(path)
    return path, accounts


def resolve_role_config(project_config: dict[str, Any], role: str | None) -> tuple[str, dict[str, Any]]:
    roles = project_config.get("roles", {})
    if role:
        if role not in roles:
            raise SystemExit(f"Unknown role {role!r} in project config")
        return role, roles[role]
    enabled_roles = project_config.get("enabled_roles", [])
    if enabled_roles:
        selected = enabled_roles[0]
        if selected in roles:
            return selected, roles[selected]
    if roles:
        selected = next(iter(roles))
        return selected, roles[selected]
    raise SystemExit("Project config has no roles configured")


def resolve_account(project_config: dict[str, Any], accounts_config: dict[str, Any], account_name: str | None = None) -> tuple[str, dict[str, Any]]:
    selected = account_name or project_config.get("account")
    if not selected:
        raise SystemExit("No account configured")
    account = accounts_config["accounts"].get(selected)
    if not isinstance(account, dict) or not account.get("bot_token"):
        raise SystemExit(f"Account {selected!r} is missing or invalid")
    return selected, account


def channel_root(project_config: dict[str, Any], channel_override: str | None = None) -> Path:
    project_id = project_config.get("project_id")
    if not project_id:
        raise SystemExit("Project config must define project_id")
    channel = channel_override or project_config.get("channel") or "main"
    return DEFAULT_DATA_ROOT / project_id / channel


def project_root(project_config: dict[str, Any]) -> Path:
    project_id = project_config.get("project_id")
    if not project_id:
        raise SystemExit("Project config must define project_id")
    return DEFAULT_DATA_ROOT / project_id


def history_path(project_config: dict[str, Any], channel_override: str | None = None) -> Path:
    return channel_root(project_config, channel_override) / "history.jsonl"


def state_path(project_config: dict[str, Any], channel_override: str | None = None) -> Path:
    return channel_root(project_config, channel_override) / "state.json"


def sessions_dir(project_config: dict[str, Any]) -> Path:
    return project_root(project_config) / "sessions"


def session_path(project_config: dict[str, Any], session_id: str) -> Path:
    return sessions_dir(project_config) / f"{session_id}.json"


def poller_path(project_config: dict[str, Any]) -> Path:
    return project_root(project_config) / "poller.json"


def poller_log_path(project_config: dict[str, Any]) -> Path:
    return project_root(project_config) / "poller.log"


def load_state(project_config: dict[str, Any], channel_override: str | None = None) -> dict[str, Any]:
    return load_json_file(state_path(project_config, channel_override), default={})


def save_state(project_config: dict[str, Any], state: dict[str, Any], channel_override: str | None = None) -> None:
    save_json_file(state_path(project_config, channel_override), state)


def list_session_records(project_config: dict[str, Any]) -> list[dict[str, Any]]:
    root = sessions_dir(project_config)
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        record = load_json_file(path, default={})
        if isinstance(record, dict):
            records.append(record)
    records.sort(key=lambda item: item.get("last_seen_at", ""), reverse=True)
    return records


def latest_seen_session(project_config: dict[str, Any], *, allow_stale: bool = False) -> dict[str, Any] | None:
    records = list_session_records(project_config)
    if not records:
        return None
    if allow_stale:
        return records[0]
    cutoff = time.time() - RECENT_SESSION_SECONDS
    for record in records:
        seen_at = record.get("last_seen_at")
        if not seen_at:
            continue
        try:
            ts = datetime.fromisoformat(seen_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if ts >= cutoff:
            return record
    return None


def resolve_session_id(
    args: argparse.Namespace,
    project_config: dict[str, Any],
    hook_payload: dict[str, Any] | None = None,
    *,
    require: bool = True,
) -> str | None:
    if getattr(args, "session_id", None):
        return args.session_id
    if hook_payload and hook_payload.get("session_id"):
        return str(hook_payload["session_id"])
    for env_name in ("AGENT_TELEGRAM_SESSION_ID", "CLAUDE_SESSION_ID"):
        if os.environ.get(env_name):
            return os.environ[env_name]
    recent = latest_seen_session(project_config, allow_stale=getattr(args, "use_latest_seen", False))
    if recent:
        return recent.get("session_id")
    if require:
        raise SystemExit("No session id available. Use --session-id or wait for SessionStart/Stop hooks to register the session.")
    return None


def upsert_session_record(project_config: dict[str, Any], session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    path = session_path(project_config, session_id)
    record = load_json_file(path, default={})
    if not isinstance(record, dict):
        record = {}
    if not record:
        record = {
            "session_id": session_id,
            "enabled": False,
            "registered_at": now_iso(),
        }
    record.update(updates)
    record["session_id"] = session_id
    record["last_seen_at"] = now_iso()
    save_json_file(path, record)
    return record


def get_session_record(project_config: dict[str, Any], session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    path = session_path(project_config, session_id)
    if not path.exists():
        return None
    record = load_json_file(path, default=None)
    return record if isinstance(record, dict) else None


def load_poller_record(project_config: dict[str, Any]) -> dict[str, Any] | None:
    path = poller_path(project_config)
    if not path.exists():
        return None
    record = load_json_file(path, default=None)
    return record if isinstance(record, dict) else None


def save_poller_record(project_config: dict[str, Any], record: dict[str, Any]) -> None:
    save_json_file(poller_path(project_config), record)


def clear_poller_record(project_config: dict[str, Any]) -> None:
    path = poller_path(project_config)
    if path.exists():
        path.unlink()


def process_command_line(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    command = result.stdout.strip()
    return command or None


def pid_is_running(pid: int | None, *, expected_substrings: list[str] | None = None) -> bool:
    if not pid or pid <= 0:
        return False
    if not _pid_alive(pid):
        return False
    if expected_substrings:
        command = process_command_line(pid)
        if not command:
            return False
        if any(fragment not in command for fragment in expected_substrings):
            return False
    return True


def poller_runtime_status(project_config: dict[str, Any]) -> dict[str, Any]:
    record = load_poller_record(project_config)
    if not record:
        return {"running": False, "record": None}
    pid_raw = record.get("pid")
    try:
        pid = int(pid_raw) if pid_raw is not None else None
    except (TypeError, ValueError):
        pid = None
    command_fragments = record.get("command_fragments")
    fragments = command_fragments if isinstance(command_fragments, list) else [str(Path(__file__).resolve()), " poll "]
    running = pid_is_running(pid, expected_substrings=fragments)
    if not running:
        record["running"] = False
    else:
        record["running"] = True
    return {"running": running, "record": record}


def stop_poller_process(project_config: dict[str, Any]) -> dict[str, Any]:
    status = poller_runtime_status(project_config)
    record = status.get("record")
    if not record:
        return {"stopped": False, "reason": "not_configured"}
    pid = record.get("pid")
    if not status.get("running"):
        clear_poller_record(project_config)
        return {"stopped": False, "reason": "not_running", "pid": pid}
    try:
        os.kill(int(pid), signal.SIGTERM)
    except OSError as exc:
        clear_poller_record(project_config)
        return {"stopped": False, "reason": f"kill_failed:{exc}", "pid": pid}
    clear_poller_record(project_config)
    return {"stopped": True, "pid": pid}


def start_poller_process(
    project_config_path: Path,
    project_config: dict[str, Any],
    *,
    session_id: str,
    interval: int,
    channel: str | None,
) -> dict[str, Any]:
    current = poller_runtime_status(project_config)
    current_record = current.get("record")
    if current.get("running") and current_record:
        if current_record.get("session_id") == session_id and int(current_record.get("interval", interval)) == interval:
            return {
                "started": False,
                "reason": "already_running",
                "pid": current_record.get("pid"),
                "session_id": session_id,
                "log_path": current_record.get("log_path"),
            }
        stop_poller_process(project_config)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--project-config",
        str(project_config_path.resolve()),
        "poll",
        "--session-id",
        session_id,
        "--interval",
        str(interval),
    ]
    if channel:
        command.extend(["--channel", channel])

    log_path = poller_log_path(project_config)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(project_config_path.parent.resolve()),
        )

    record = {
        "pid": proc.pid,
        "session_id": session_id,
        "interval": interval,
        "channel": channel or project_config.get("channel") or "main",
        "started_at": now_iso(),
        "log_path": str(log_path),
        "command_fragments": [str(Path(__file__).resolve()), " poll ", f"--session-id {session_id}"],
    }
    save_poller_record(project_config, record)
    return {
        "started": True,
        "pid": proc.pid,
        "session_id": session_id,
        "interval": interval,
        "log_path": str(log_path),
    }


def append_history(project_config: dict[str, Any], record: dict[str, Any], channel_override: str | None = None) -> None:
    path = history_path(project_config, channel_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True))
        handle.write("\n")


def load_history(project_config: dict[str, Any], channel_override: str | None = None) -> list[dict[str, Any]]:
    path = history_path(project_config, channel_override)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                records.append(entry)
    return records


def save_history(project_config: dict[str, Any], records: list[dict[str, Any]], channel_override: str | None = None) -> None:
    path = history_path(project_config, channel_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def message_key(record: dict[str, Any]) -> str:
    transcription = record.get("transcription") or {}
    transcription_status = transcription.get("status", "")
    return f"{record.get('direction')}:{record.get('message_id')}:{record.get('update_id', '')}:{transcription_status}"


def telegram_message_timestamp_iso(message: dict[str, Any]) -> str:
    raw = message.get("date")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, timezone.utc).isoformat().replace("+00:00", "Z")
    return now_iso()


def normalize_text(message: dict[str, Any]) -> str:
    text = message.get("text") or message.get("caption")
    if text:
        return str(text)
    return "<non-text message>"


def normalize_sender(message: dict[str, Any]) -> str:
    sender = message.get("from") or {}
    return sender.get("username") or sender.get("first_name") or sender.get("id") or "unknown"


def voice_config(project_config: dict[str, Any]) -> dict[str, Any]:
    raw = project_config.get("voice_transcription")
    return raw if isinstance(raw, dict) else {}


def tts_config(project_config: dict[str, Any]) -> dict[str, Any]:
    raw = project_config.get("voice_synthesis")
    return raw if isinstance(raw, dict) else {}


def media_label(record: dict[str, Any]) -> str:
    media_type = record.get("media_type")
    transcription = record.get("transcription") or {}
    if media_type == "voice":
        status = transcription.get("status")
        if status == "completed":
            return "[voice]"
        if status == "pending":
            return "[voice pending]"
        if status == "failed":
            return "[voice failed]"
        return "[voice]"
    return ""


def record_text(record: dict[str, Any]) -> str:
    text = str(record.get("text", ""))
    label = media_label(record)
    return f"{label} {text}".strip() if label else text


def build_inbound_record(project_config: dict[str, Any], channel: str, message: dict[str, Any], update_id: int) -> dict[str, Any]:
    chat = message.get("chat") or {}
    voice = message.get("voice")
    record = {
        "direction": "inbound",
        "timestamp": telegram_message_timestamp_iso(message),
        "project_id": project_config["project_id"],
        "channel": channel,
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


def speak2_request(base_url: str, session_token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    root = base_url.rstrip("/")
    url = f"{root}{path}"
    headers = {
        "Accept": "application/json",
        "X-Speak2-Session-Token": session_token,
    }
    data = None
    request_method = method.upper()
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=request_method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw or f"http_{exc.code}"}
        return exc.code, payload if isinstance(payload, dict) else {"error": str(payload)}
    except urllib.error.URLError as exc:
        return 503, {"error": f"connection_error:{exc.reason}"}


def kokoro_request(base_url: str, session_token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    root = base_url.rstrip("/")
    url = f"{root}{path}"
    headers = {
        "Accept": "application/json",
        "X-Kokoro-Session-Token": session_token,
    }
    data = None
    request_method = method.upper()
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=request_method)
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace").strip()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"error": raw or f"http_{exc.code}"}
        return exc.code, parsed if isinstance(parsed, dict) else {"error": str(parsed)}
    except urllib.error.URLError as exc:
        return 503, {"error": f"connection_error:{exc.reason}"}


def download_telegram_file(bot_token: str, file_id: str) -> Path:
    file_info = api_request(bot_token, "getFile", {"file_id": file_id})["result"]
    file_path = file_info.get("file_path")
    if not file_path:
        raise RuntimeError("telegram_file_path_missing")
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    suffix = Path(str(file_path)).suffix or ".bin"
    with urllib.request.urlopen(url, timeout=60) as response, tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(response.read())
        return Path(handle.name)


def convert_audio_to_wav(input_path: Path, ffmpeg_path: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
        output_path = Path(handle.name)
    result = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg_failed:{result.stderr.strip() or result.stdout.strip()}")
    return output_path


def convert_audio_to_telegram_voice(input_path: Path, ffmpeg_path: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as handle:
        output_path = Path(handle.name)
    result = subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg_voice_failed:{result.stderr.strip() or result.stdout.strip()}")
    return output_path


def transcribe_voice_file(project_config: dict[str, Any], audio_path: Path, *, message_id: str | None = None) -> dict[str, Any]:
    config = voice_config(project_config)
    status, payload = speak2_request(
        str(config.get("base_url") or DEFAULT_SPEAK2_BASE_URL),
        str(config.get("session_token") or DEFAULT_SPEAK2_SESSION_TOKEN),
        "POST",
        "/v1/transcription/file",
        {
            "audio_path": str(audio_path),
            "language": str(config.get("language") or "en"),
            "source": "telegram",
            "message_id": message_id,
        },
    )
    if status == 200 and payload.get("ok"):
        return {
            "status": "completed",
            "text": payload.get("text") or "",
            "provider": "speak2",
            "engine": payload.get("model"),
            "language": payload.get("language"),
            "duration_seconds": payload.get("duration_seconds"),
            "error": None,
            "last_attempt_at": now_iso(),
        }
    if status == 503:
        return {
            "status": "pending",
            "text": None,
            "provider": "speak2",
            "engine": payload.get("model"),
            "language": payload.get("language"),
            "duration_seconds": payload.get("duration_seconds"),
            "error": payload.get("error"),
            "last_attempt_at": now_iso(),
        }
    return {
        "status": "failed",
        "text": None,
        "provider": "speak2",
        "engine": payload.get("model"),
        "language": payload.get("language"),
        "duration_seconds": payload.get("duration_seconds"),
        "error": payload.get("error") or f"http_{status}",
        "last_attempt_at": now_iso(),
    }


def apply_voice_transcription(record: dict[str, Any], project_config: dict[str, Any], account: dict[str, Any]) -> None:
    voice = record.get("voice") or {}
    file_id = voice.get("file_id")
    if not file_id or not voice_config(project_config).get("enabled", True):
        record["text"] = "<voice note>"
        return

    source_path: Path | None = None
    wav_path: Path | None = None
    try:
        source_path = download_telegram_file(account["bot_token"], str(file_id))
        wav_path = convert_audio_to_wav(source_path, str(voice_config(project_config).get("ffmpeg_path") or DEFAULT_FFMPEG_PATH))
        transcription = transcribe_voice_file(project_config, wav_path, message_id=str(record.get("message_id")))
    except Exception as exc:
        transcription = {
            "status": "failed",
            "text": None,
            "provider": "speak2",
            "engine": None,
            "language": str(voice_config(project_config).get("language") or "en"),
            "duration_seconds": voice.get("duration_seconds"),
            "error": str(exc),
            "last_attempt_at": now_iso(),
        }
    finally:
        if source_path:
            source_path.unlink(missing_ok=True)
        if wav_path:
            wav_path.unlink(missing_ok=True)

    record["transcription"] = transcription
    if transcription["status"] == "completed" and transcription.get("text"):
        record["text"] = str(transcription["text"])
    elif transcription["status"] == "pending":
        record["text"] = "<voice note: transcription pending>"
    else:
        record["text"] = "<voice note: transcription failed>"


def retry_pending_voice_records(project_config: dict[str, Any], account: dict[str, Any], *, channel_override: str | None = None) -> int:
    records = load_history(project_config, channel_override)
    updated = 0
    for record in records:
        if record.get("direction") != "inbound" or record.get("media_type") != "voice":
            continue
        transcription = record.get("transcription") or {}
        if transcription.get("status") != "pending":
            continue
        apply_voice_transcription(record, project_config, account)
        updated += 1
    if updated:
        save_history(project_config, records, channel_override)
    return updated


def build_outbound_record(
    project_config: dict[str, Any],
    channel: str,
    agent_name: str,
    chat_id: str,
    result: dict[str, Any],
    *,
    text: str,
    media_type: str = "text",
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message = result["result"]
    record = {
        "direction": "outbound",
        "timestamp": now_iso(),
        "project_id": project_config["project_id"],
        "channel": channel,
        "agent_name": agent_name,
        "chat_id": str(chat_id),
        "message_id": str(message["message_id"]),
        "update_id": None,
        "sender_label": agent_name,
        "text": text,
        "read": True,
        "media_type": media_type,
    }
    if extras:
        record.update(extras)
    return record


def api_request(token: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    headers = {}
    if params:
        encoded = {key: str(value) for key, value in params.items() if value is not None}
        data = urllib.parse.urlencode(encoded).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Telegram API HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Telegram API connection error: {exc}") from exc
    if not payload.get("ok"):
        raise SystemExit(f"Telegram API error: {json.dumps(payload, indent=2)}")
    return payload


def api_multipart_request(token: str, method: str, fields: dict[str, Any], file_field: str, file_path: Path) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    boundary = f"----agenttelegram{int(time.time() * 1000)}"
    body = bytearray()

    for key, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = urllib.request.Request(url, data=bytes(body), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Telegram API HTTP error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Telegram API connection error: {exc}") from exc
    if not payload.get("ok"):
        raise SystemExit(f"Telegram API error: {json.dumps(payload, indent=2)}")
    return payload


def sync_updates(
    project_config: dict[str, Any],
    account: dict[str, Any],
    *,
    channel_override: str | None = None,
) -> dict[str, Any]:
    channel = channel_override or project_config.get("channel") or "main"
    state = load_state(project_config, channel_override)
    retried_pending = retry_pending_voice_records(project_config, account, channel_override=channel_override)
    params: dict[str, Any] = {"timeout": 1}
    if state.get("next_update_id") is not None:
        params["offset"] = state["next_update_id"]
    payload = api_request(account["bot_token"], "getUpdates", params)
    new_records: list[dict[str, Any]] = []
    for update in payload.get("result", []):
        update_id = int(update["update_id"])
        state["next_update_id"] = update_id + 1
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") or {}
        configured_chat = str(project_config.get("chat_id") or account.get("default_chat_id") or "")
        chat_id = str(chat.get("id"))
        if configured_chat and chat_id != configured_chat:
            continue
        record = build_inbound_record(project_config, channel, message, update_id)
        if record.get("media_type") == "voice":
            apply_voice_transcription(record, project_config, account)
        new_records.append(record)
    if new_records:
        for record in new_records:
            append_history(project_config, record, channel_override)
    state["last_sync_at"] = now_iso()
    save_state(project_config, state, channel_override)
    unread_count = len([record for record in load_history(project_config, channel_override) if record.get("direction") == "inbound" and not record.get("read")])
    return {
        "synced": len(new_records),
        "retried_pending_voice": retried_pending,
        "next_update_id": state.get("next_update_id"),
        "last_sync_at": state.get("last_sync_at"),
        "unread_count": unread_count,
        "records": new_records,
    }


def format_record_plain(record: dict[str, Any]) -> str:
    ts = record.get("timestamp", "")
    direction = record.get("direction", "")
    sender = record.get("sender_label") or record.get("agent_name") or "unknown"
    text = record_text(record)
    return f"{ts} {direction} {sender}: {text}"


def read_message_input(args: argparse.Namespace) -> str:
    message = args.message
    if getattr(args, "stdin", False):
        stdin_text = sys.stdin.read()
        message = stdin_text if message is None else f"{message}\n{stdin_text}"
    if not message:
        raise SystemExit("Message text is required")
    return message.rstrip("\n")


def tmux_target(role_config: dict[str, Any], session_record: dict[str, Any] | None) -> str | None:
    if session_record and session_record.get("tmux_session"):
        return str(session_record["tmux_session"])
    if role_config.get("tmux_session"):
        return str(role_config["tmux_session"])
    return None


def run_tmux(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    server_flags = ["-L", _tmux_server] if _tmux_server else []
    return subprocess.run(
        ["tmux", *server_flags, *args],
        check=False,
        text=True,
        input=input_text,
        capture_output=True,
    )


def tmux_notify(target: str, text: str) -> None:
    result = run_tmux(["display-message", "-t", target, text])
    if result.returncode != 0:
        raise SystemExit(f"tmux notify failed: {result.stderr.strip() or result.stdout.strip()}")


def resolve_tmux_pane(target: str) -> str:
    result = run_tmux(["display-message", "-p", "-t", target, "#{pane_id}"])
    if result.returncode != 0:
        raise SystemExit(f"tmux pane resolution failed: {result.stderr.strip() or result.stdout.strip()}")
    pane_id = result.stdout.strip()
    if not pane_id:
        raise SystemExit(f"tmux pane resolution returned no pane for target {target!r}")
    return pane_id


def tmux_inject(target: str, text: str) -> None:
    pane_target = resolve_tmux_pane(target)
    buffer_name = f"agent-telegram-{int(time.time() * 1000)}"
    load = run_tmux(["load-buffer", "-b", buffer_name, "-"], input_text=text)
    if load.returncode != 0:
        raise SystemExit(f"tmux load-buffer failed: {load.stderr.strip() or load.stdout.strip()}")
    paste = run_tmux(["paste-buffer", "-p", "-t", pane_target, "-b", buffer_name, "-d"])
    if paste.returncode != 0:
        raise SystemExit(f"tmux paste-buffer failed: {paste.stderr.strip() or paste.stdout.strip()}")
    # Wait for the paste to be processed by the terminal before sending Enter.
    # Without this delay, the terminal may not have received the text yet and
    # Enter fires on an empty prompt. 2 seconds is the minimum reliable delay.
    time.sleep(2)
    send = run_tmux(["send-keys", "-t", pane_target, "Enter"])
    if send.returncode != 0:
        raise SystemExit(f"tmux send-keys failed: {send.stderr.strip() or send.stdout.strip()}")
    # Safety Enter — ensures submission if the first Enter arrived before the
    # terminal finished processing the pasted text. Claude Code ignores blank inputs.
    time.sleep(2)
    run_tmux(["send-keys", "-t", pane_target, "Enter"])


def latest_unread(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    unread = [record for record in records if record.get("direction") == "inbound" and not record.get("read")]
    return unread[-1] if unread else None


def maybe_deliver(
    project_config: dict[str, Any],
    role: str,
    role_config: dict[str, Any],
    session_record: dict[str, Any],
    *,
    channel_override: str | None = None,
) -> dict[str, Any]:
    records = load_history(project_config, channel_override)
    latest = latest_unread(records)
    if latest is None:
        return {"delivered": False, "reason": "no_unread"}

    state = load_state(project_config, channel_override)
    deliveries = state.setdefault("deliveries", {})
    role_delivery = deliveries.setdefault(role, {})
    record_key = message_key(latest)
    if role_delivery.get("last_message_key") == record_key:
        return {"delivered": False, "reason": "already_delivered", "message_key": record_key}

    mode = role_config.get("inbound_mode", "notify")
    target = tmux_target(role_config, session_record)
    if mode == "inject":
        if not target:
            raise SystemExit(f"Role {role} is configured for inject mode but has no tmux session")
        formatted = f"[Telegram][{project_config['project_id']}/{latest['channel']}][{latest['sender_label']}] {record_text(latest)}"
        tmux_inject(target, formatted)
    else:
        summary = f"Telegram message waiting for {project_config['project_id']}/{latest['channel']} from {latest['sender_label']}"
        if target:
            tmux_notify(target, summary)
        else:
            print(summary)

    role_delivery["last_message_key"] = record_key
    role_delivery["last_delivered_at"] = now_iso()
    save_state(project_config, state, channel_override)
    return {"delivered": True, "mode": mode, "message_key": record_key, "target": target}


def should_debounce(project_config: dict[str, Any], hook_payload: dict[str, Any], channel_override: str | None = None) -> bool:
    if hook_payload.get("hook_event_name") == "SessionStart":
        return False
    state = load_state(project_config, channel_override)
    last_checked = state.get("last_hook_check_at")
    if not last_checked:
        return False
    try:
        last_ts = datetime.fromisoformat(last_checked.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return (time.time() - last_ts) < int(project_config.get("hook_debounce_seconds", 30))


def touch_hook_check(project_config: dict[str, Any], channel_override: str | None = None) -> None:
    state = load_state(project_config, channel_override)
    state["last_hook_check_at"] = now_iso()
    save_state(project_config, state, channel_override)


def tts_health(project_config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    config = tts_config(project_config)
    return kokoro_request(
        str(config.get("base_url") or DEFAULT_KOKORO_BASE_URL),
        str(config.get("session_token") or DEFAULT_KOKORO_SESSION_TOKEN),
        "GET",
        "/v1/tts/health",
    )


def build_spoken_text(agent_name: str, message: str, *, raw: bool) -> str:
    return message if raw else f"{agent_name}. {message}"


def synthesize_voice_message(project_config: dict[str, Any], text: str, *, voice: str | None = None, speed: float | None = None) -> dict[str, Any]:
    config = tts_config(project_config)
    status, payload = kokoro_request(
        str(config.get("base_url") or DEFAULT_KOKORO_BASE_URL),
        str(config.get("session_token") or DEFAULT_KOKORO_SESSION_TOKEN),
        "POST",
        "/v1/tts/speak",
        {
            "text": text,
            "voice": voice or str(config.get("default_voice") or DEFAULT_KOKORO_VOICE),
            "speed": speed if speed is not None else float(config.get("default_speed") or DEFAULT_KOKORO_SPEED),
            "language": str(config.get("language") or DEFAULT_KOKORO_LANGUAGE),
            "source": "telegram",
        },
    )
    if status == 200 and payload.get("ok"):
        return payload
    error = payload.get("error") or f"http_{status}"
    raise SystemExit(f"Kokoro TTS error: {error}")


def cmd_account_test(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    account_name, account = resolve_account(project_config, accounts_config, args.account)
    me = api_request(account["bot_token"], "getMe")["result"]
    payload = {
        "account": account_name,
        "bot_username": me.get("username"),
        "bot_id": me.get("id"),
        "ok": True,
    }
    return emit(args, payload, default_plain=f"ok account={account_name} bot=@{me.get('username')}")


def cmd_config_validate(args: argparse.Namespace) -> int:
    project_path, project_config = load_project_config(args.project_config)
    account_path, accounts_config = load_accounts(args.accounts_config)
    account_name, account = resolve_account(project_config, accounts_config)
    enabled_roles = project_config.get("enabled_roles", [])
    roles = project_config.get("roles", {})
    issues: list[str] = []

    if not project_config.get("project_id"):
        issues.append("project_id is required")
    if not project_config.get("chat_id") and not account.get("default_chat_id"):
        issues.append("chat_id is required either in project config or account config")
    for role in enabled_roles:
        if role not in roles:
            issues.append(f"enabled role {role!r} has no role config")
    for role_name, role_config in roles.items():
        if role_config.get("inbound_mode") not in (None, "notify", "inject"):
            issues.append(f"role {role_name!r} has invalid inbound_mode")
        if role_config.get("inbound_mode") == "inject" and not role_config.get("tmux_session"):
            issues.append(f"role {role_name!r} uses inject mode but has no tmux_session")
    ffmpeg_path = str(voice_config(project_config).get("ffmpeg_path") or DEFAULT_FFMPEG_PATH)
    if voice_config(project_config).get("enabled", True) and not Path(ffmpeg_path).exists():
        issues.append(f"voice transcription ffmpeg path does not exist: {ffmpeg_path}")
    synthesis_ffmpeg = str(tts_config(project_config).get("ffmpeg_path") or DEFAULT_FFMPEG_PATH)
    if tts_config(project_config).get("enabled", True) and not Path(synthesis_ffmpeg).exists():
        issues.append(f"voice synthesis ffmpeg path does not exist: {synthesis_ffmpeg}")

    payload = {
        "project_config": str(project_path),
        "accounts_config": str(account_path),
        "account": account_name,
        "issues": issues,
        "valid": not issues,
    }
    if issues:
        return emit(args, payload, default_plain="invalid\n" + "\n".join(f"- {issue}" for issue in issues))
    return emit(args, payload, default_plain=f"ok project={project_config['project_id']} account={account_name}")


def cmd_send(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    channel = args.channel or project_config.get("channel") or "main"
    role, role_config = resolve_role_config(project_config, args.role)
    _, account = resolve_account(project_config, accounts_config)
    chat_id = str(args.chat_id or project_config.get("chat_id") or account.get("default_chat_id") or "")
    if not chat_id:
        raise SystemExit("No chat_id configured")

    agent_name = args.agent_name or role_config.get("agent_name") or role
    message = read_message_input(args)
    outgoing_text = message if args.raw else f"[{agent_name}] {message}"
    payload = api_request(
        account["bot_token"],
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": outgoing_text,
            "disable_web_page_preview": str(bool(args.disable_preview)).lower(),
            "disable_notification": str(bool(args.silent)).lower(),
        },
    )
    record = build_outbound_record(project_config, channel, agent_name, chat_id, payload, text=outgoing_text)
    append_history(project_config, record, channel)
    return emit(
        args,
        {"sent": True, "message_id": record["message_id"], "chat_id": chat_id, "agent_name": agent_name},
        default_plain=f"sent message_id={record['message_id']} chat_id={chat_id} agent={agent_name}",
    )


def cmd_tts_health(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    status, payload = tts_health(project_config)
    payload["http_status"] = status
    plain = "ok" if payload.get("ok") else f"not_ready error={payload.get('error')}"
    return emit(args, payload, default_plain=plain)


def cmd_send_voice(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    channel = args.channel or project_config.get("channel") or "main"
    role, role_config = resolve_role_config(project_config, args.role)
    _, account = resolve_account(project_config, accounts_config)
    chat_id = str(args.chat_id or project_config.get("chat_id") or account.get("default_chat_id") or "")
    if not chat_id:
        raise SystemExit("No chat_id configured")
    if not tts_config(project_config).get("enabled", True):
        raise SystemExit("Voice synthesis is disabled in project config")

    agent_name = args.agent_name or role_config.get("agent_name") or role
    message = read_message_input(args)
    spoken_text = build_spoken_text(agent_name, message, raw=bool(args.raw))
    voice_name = args.voice or str(tts_config(project_config).get("default_voice") or DEFAULT_KOKORO_VOICE)
    speed = args.speed if args.speed is not None else float(tts_config(project_config).get("default_speed") or DEFAULT_KOKORO_SPEED)
    if not getattr(args, "json", False):
        print("Synthesizing voice note. Longer messages may take a moment to process.", file=sys.stderr)

    wav_path: Path | None = None
    telegram_voice_path: Path | None = None
    try:
        synthesis = synthesize_voice_message(project_config, spoken_text, voice=voice_name, speed=speed)
        wav_path = Path(str(synthesis.get("audio_path") or "")).expanduser()
        if not wav_path.exists():
            raise SystemExit("Kokoro TTS did not return a valid audio file")
        telegram_voice_path = convert_audio_to_telegram_voice(
            wav_path,
            str(tts_config(project_config).get("ffmpeg_path") or DEFAULT_FFMPEG_PATH),
        )
        payload = api_multipart_request(
            account["bot_token"],
            "sendVoice",
            {
                "chat_id": chat_id,
                "disable_notification": str(bool(args.silent)).lower(),
            },
            "voice",
            telegram_voice_path,
        )
        record = build_outbound_record(
            project_config,
            channel,
            agent_name,
            chat_id,
            payload,
            text=spoken_text,
            media_type="voice",
            extras={
                "tts": {
                    "provider": "kokoro",
                    "voice": synthesis.get("voice") or voice_name,
                    "speed": speed,
                    "language": synthesis.get("language") or str(tts_config(project_config).get("language") or DEFAULT_KOKORO_LANGUAGE),
                    "duration_seconds": synthesis.get("duration_seconds"),
                },
                "voice": {
                    "mime_type": "audio/ogg",
                    "file_id": payload["result"].get("voice", {}).get("file_id"),
                    "file_unique_id": payload["result"].get("voice", {}).get("file_unique_id"),
                    "duration_seconds": payload["result"].get("voice", {}).get("duration"),
                    "file_size": payload["result"].get("voice", {}).get("file_size"),
                },
            },
        )
        append_history(project_config, record, channel)
    finally:
        if telegram_voice_path:
            telegram_voice_path.unlink(missing_ok=True)
        if wav_path:
            wav_path.unlink(missing_ok=True)

    return emit(
        args,
        {"sent": True, "message_id": record["message_id"], "chat_id": chat_id, "agent_name": agent_name, "media_type": "voice"},
        default_plain=f"sent voice message_id={record['message_id']} chat_id={chat_id} agent={agent_name}",
    )


def cmd_send_photo(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    channel = getattr(args, "channel", None) or project_config.get("channel") or "main"
    role, role_config = resolve_role_config(project_config, getattr(args, "role", None))
    _, account = resolve_account(project_config, accounts_config)
    chat_id = str(getattr(args, "chat_id", None) or project_config.get("chat_id") or account.get("default_chat_id") or "")
    if not chat_id:
        raise SystemExit("No chat_id configured")
    agent_name = getattr(args, "agent_name", None) or role_config.get("agent_name") or role
    photo_path = Path(args.photo).expanduser()
    if not photo_path.exists():
        raise SystemExit(f"Photo file not found: {photo_path}")
    caption = f"[{agent_name}] {args.caption}" if args.caption else f"[{agent_name}]"
    payload = api_multipart_request(
        account["bot_token"],
        "sendPhoto",
        {"chat_id": chat_id, "caption": caption},
        "photo",
        photo_path,
    )
    record = build_outbound_record(project_config, channel, agent_name, chat_id, payload, text=caption, media_type="photo")
    append_history(project_config, record, channel)
    return emit(
        args,
        {"sent": True, "message_id": record["message_id"], "chat_id": chat_id, "agent_name": agent_name, "media_type": "photo"},
        default_plain=f"sent photo message_id={record['message_id']} chat_id={chat_id} agent={agent_name}",
    )


def cmd_send_video(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    channel = getattr(args, "channel", None) or project_config.get("channel") or "main"
    role, role_config = resolve_role_config(project_config, getattr(args, "role", None))
    _, account = resolve_account(project_config, accounts_config)
    chat_id = str(getattr(args, "chat_id", None) or project_config.get("chat_id") or account.get("default_chat_id") or "")
    if not chat_id:
        raise SystemExit("No chat_id configured")
    agent_name = getattr(args, "agent_name", None) or role_config.get("agent_name") or role
    video_path = Path(args.video).expanduser()
    if not video_path.exists():
        raise SystemExit(f"Video file not found: {video_path}")
    caption = f"[{agent_name}] {args.caption}" if args.caption else f"[{agent_name}]"
    payload = api_multipart_request(
        account["bot_token"],
        "sendVideo",
        {"chat_id": chat_id, "caption": caption},
        "video",
        video_path,
    )
    record = build_outbound_record(project_config, channel, agent_name, chat_id, payload, text=caption, media_type="video")
    append_history(project_config, record, channel)
    return emit(
        args,
        {"sent": True, "message_id": record["message_id"], "chat_id": chat_id, "agent_name": agent_name, "media_type": "video"},
        default_plain=f"sent video message_id={record['message_id']} chat_id={chat_id} agent={agent_name}",
    )


def cmd_sync(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    _, account = resolve_account(project_config, accounts_config)
    payload = sync_updates(project_config, account, channel_override=args.channel)
    plain = f"synced={payload['synced']} retried_voice={payload['retried_pending_voice']} unread={payload['unread_count']}"
    return emit(args, payload, default_plain=plain)


def cmd_voice_status(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    records = history_subset(
        project_config,
        channel_override=args.channel,
        direction="inbound",
        unread_only=False,
        limit=args.limit,
    )
    voice_records = [record for record in records if record.get("media_type") == "voice"]
    payload = [
        {
            "message_id": record.get("message_id"),
            "timestamp": record.get("timestamp"),
            "sender_label": record.get("sender_label"),
            "status": (record.get("transcription") or {}).get("status"),
            "error": (record.get("transcription") or {}).get("error"),
            "text": record.get("text"),
        }
        for record in voice_records
    ]
    if getattr(args, "json", False):
        return emit(args, payload)
    if not payload:
        print("no voice messages")
        return 0
    for item in payload:
        print(
            f"{item['timestamp']} inbound {item['sender_label']}: "
            f"{item['status']} {item['text']}"
        )
    return 0


def history_subset(
    project_config: dict[str, Any],
    *,
    channel_override: str | None,
    direction: str | None,
    unread_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    records = load_history(project_config, channel_override)
    if direction:
        records = [record for record in records if record.get("direction") == direction]
    if unread_only:
        records = [record for record in records if not record.get("read")]
    records = sorted(records, key=lambda item: (item.get("timestamp", ""), item.get("update_id") or ""), reverse=True)
    if limit is not None:
        records = records[:limit]
    return records


def cmd_latest(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    records = history_subset(project_config, channel_override=args.channel, direction=args.direction, unread_only=False, limit=1)
    if not records:
        return emit(args, {"message": None}, default_plain="no messages")
    return emit(args, records[0], default_plain=format_record_plain(records[0]))


def cmd_history(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    records = history_subset(
        project_config,
        channel_override=args.channel,
        direction=args.direction,
        unread_only=False,
        limit=args.limit,
    )
    if getattr(args, "json", False):
        return emit(args, records)
    if not records:
        print("no messages")
        return 0
    for record in records:
        print(format_record_plain(record))
    return 0


def cmd_unread(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    records = history_subset(
        project_config,
        channel_override=args.channel,
        direction="inbound",
        unread_only=True,
        limit=args.limit,
    )
    if getattr(args, "json", False):
        return emit(args, records)
    if not records:
        print("no unread messages")
        return 0
    for record in records:
        print(format_record_plain(record))
    return 0


def cmd_mark_read(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    records = load_history(project_config, args.channel)
    updated = 0
    for record in records:
        if record.get("direction") != "inbound" or record.get("read"):
            continue
        if args.all or str(record.get("message_id")) == str(args.message_id):
            record["read"] = True
            updated += 1
    save_history(project_config, records, args.channel)
    return emit(args, {"updated": updated}, default_plain=f"marked_read={updated}")


def cmd_enable_session(args: argparse.Namespace) -> int:
    project_path, project_config = load_project_config(args.project_config)
    role, role_config = resolve_role_config(project_config, args.role)
    session_id = resolve_session_id(args, project_config)
    target = args.tmux_session or role_config.get("tmux_session")
    record = upsert_session_record(
        project_config,
        session_id,
        {
            "role": role,
            "enabled": True,
            "tmux_session": target,
        },
    )
    payload: dict[str, Any] = {"session": record}
    plain = f"enabled session={session_id} role={role} tmux={target or '-'}"
    if getattr(args, "start_poller", False):
        poller = start_poller_process(
            project_path,
            project_config,
            session_id=session_id,
            interval=args.poll_interval,
            channel=args.channel,
        )
        payload["poller"] = poller
        if poller.get("started"):
            plain = f"{plain} poller_pid={poller['pid']}"
        else:
            plain = f"{plain} poller={poller.get('reason')}"
    return emit(args, payload, default_plain=plain)


def cmd_disable_session(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    session_id = resolve_session_id(args, project_config)
    record = upsert_session_record(project_config, session_id, {"enabled": False})
    payload: dict[str, Any] = {"session": record}
    plain = f"disabled session={session_id}"
    if getattr(args, "stop_poller", False):
        poller = load_poller_record(project_config)
        if poller and poller.get("session_id") == session_id:
            stop_payload = stop_poller_process(project_config)
            payload["poller"] = stop_payload
            plain = f"{plain} poller_stopped={stop_payload.get('stopped')}"
    return emit(args, payload, default_plain=plain)


def cmd_session_status(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    if args.all:
        records = list_session_records(project_config)
        return emit(args, records, default_plain="\n".join(json.dumps(record, ensure_ascii=True) for record in records) if records else "no sessions")
    session_id = resolve_session_id(args, project_config, require=False)
    record = get_session_record(project_config, session_id) if session_id else latest_seen_session(project_config, allow_stale=True)
    if not record:
        return emit(args, {"session": None}, default_plain="no session record")
    return emit(
        args,
        record,
        default_plain=f"session={record.get('session_id')} enabled={record.get('enabled')} role={record.get('role') or '-'} tmux={record.get('tmux_session') or '-'}",
    )


def cmd_poller_start(args: argparse.Namespace) -> int:
    project_path, project_config = load_project_config(args.project_config)
    comm_mode = project_config.get("communication_mode", "local-poller")
    if comm_mode == "central-router":
        if check_router_alive():
            payload = {"started": False, "reason": "central_router_running",
                       "message": "Central router is running, local poller not needed"}
            return emit(args, payload, default_plain="Central router is running, local poller not needed")
        print("WARNING: Central router not running, starting local poller as fallback")
    session_id = resolve_session_id(args, project_config)
    session_record = get_session_record(project_config, session_id)
    if not session_record or not session_record.get("enabled"):
        raise SystemExit("Selected session is not enabled")
    payload = start_poller_process(
        project_path,
        project_config,
        session_id=session_id,
        interval=args.interval,
        channel=args.channel,
    )
    plain = (
        f"poller_started pid={payload['pid']} session={payload['session_id']}"
        if payload.get("started")
        else f"poller={payload.get('reason')} pid={payload.get('pid', '-')}"
    )
    return emit(args, payload, default_plain=plain)


def cmd_poller_status(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    payload = poller_runtime_status(project_config)
    record = payload.get("record")
    if not record:
        return emit(args, payload, default_plain="poller not configured")
    plain = (
        f"poller running={payload['running']} pid={record.get('pid')} "
        f"session={record.get('session_id')} interval={record.get('interval')}"
    )
    return emit(args, payload, default_plain=plain)


def cmd_poller_stop(args: argparse.Namespace) -> int:
    _, project_config = load_project_config(args.project_config)
    payload = stop_poller_process(project_config)
    plain = (
        f"poller_stopped pid={payload.get('pid')}"
        if payload.get("stopped")
        else f"poller_stop={payload.get('reason')}"
    )
    return emit(args, payload, default_plain=plain)


def cmd_hook_check(args: argparse.Namespace) -> int:
    project_path, project_config = load_project_config(args.project_config)
    _, accounts_config = load_accounts(args.accounts_config)
    _, account = resolve_account(project_config, accounts_config)
    hook_payload = read_stdin_json() if args.stdin_hook or not sys.stdin.isatty() else {}

    session_id = resolve_session_id(args, project_config, hook_payload, require=False)
    if session_id:
        upsert_session_record(
            project_config,
            session_id,
            {
                "last_hook_event": hook_payload.get("hook_event_name"),
                "transcript_path": hook_payload.get("transcript_path"),
                "cwd": hook_payload.get("cwd") or str(project_path.parent.resolve()),
            },
        )

    if hook_payload.get("hook_event_name") == "Stop" and hook_payload.get("stop_hook_active"):
        return emit(args, {"skipped": "stop_hook_active"}, default_plain="skipped stop_hook_active")

    session_record = get_session_record(project_config, session_id) if session_id else None
    if not session_record or not session_record.get("enabled"):
        return emit(args, {"skipped": "session_not_enabled"}, default_plain="skipped session_not_enabled")

    role = session_record.get("role")
    if not role or role not in project_config.get("enabled_roles", []):
        return emit(args, {"skipped": "role_not_enabled"}, default_plain="skipped role_not_enabled")

    role_config = project_config.get("roles", {}).get(role)
    if not isinstance(role_config, dict):
        return emit(args, {"skipped": "role_missing"}, default_plain="skipped role_missing")

    if should_debounce(project_config, hook_payload, channel_override=args.channel):
        return emit(args, {"skipped": "debounced"}, default_plain="skipped debounced")

    # If central-router mode and router is alive, skip local sync — router handles it
    comm_mode = project_config.get("communication_mode", "local-poller")
    if comm_mode == "central-router" and check_router_alive():
        return emit(args, {"skipped": "central_router_active"}, default_plain="skipped central_router_active")

    touch_hook_check(project_config, args.channel)
    sync_payload = sync_updates(project_config, account, channel_override=args.channel)
    delivery_payload = maybe_deliver(project_config, role, role_config, session_record, channel_override=args.channel)
    return emit(
        args,
        {"sync": sync_payload, "delivery": delivery_payload, "session_id": session_id, "role": role},
        default_plain=f"session={session_id} synced={sync_payload['synced']} delivered={delivery_payload.get('delivered', False)}",
    )


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
        try:
            cmd_hook_check(args)
        except SystemExit as exc:
            detail = str(exc) or exc.__class__.__name__
            print(f"poll_error={detail}")
        except Exception as exc:
            print(f"poll_error={exc.__class__.__name__}: {exc}")
        if deadline is not None and time.time() >= deadline:
            return 0
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    def add_json_flag(target: argparse.ArgumentParser) -> None:
        target.add_argument("--json", action="store_true", help="Emit JSON output")

    parser = argparse.ArgumentParser(description="Project-scoped Telegram gateway for agents")
    add_json_flag(parser)
    parser.add_argument("--project-config", help="Path to .agent-comms/telegram.json")
    parser.add_argument("--accounts-config", help="Path to ~/.config/agent-telegram/accounts.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    account_test = subparsers.add_parser("account", help="Account operations")
    add_json_flag(account_test)
    account_test_sub = account_test.add_subparsers(dest="account_command", required=True)
    account_test_run = account_test_sub.add_parser("test", help="Verify the configured Telegram account")
    add_json_flag(account_test_run)
    account_test_run.add_argument("--account", help="Override account name")
    account_test_run.set_defaults(func=cmd_account_test)

    config = subparsers.add_parser("config", help="Configuration operations")
    add_json_flag(config)
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate", help="Validate project and account config")
    add_json_flag(config_validate)
    config_validate.set_defaults(func=cmd_config_validate)

    send = subparsers.add_parser("send", help="Send a Telegram message")
    add_json_flag(send)
    send.add_argument("--role", help="Role to attribute the message to")
    send.add_argument("--agent-name", help="Override visible sender label")
    send.add_argument("--chat-id", help="Override target chat id")
    send.add_argument("--channel", help="Override logical channel")
    send.add_argument("--message", help="Message text")
    send.add_argument("--stdin", action="store_true", help="Read or append message text from stdin")
    send.add_argument("--silent", action="store_true", help="Send without notification sound")
    send.add_argument("--disable-preview", action="store_true", help="Disable link previews")
    send.add_argument("--raw", action="store_true", help="Do not prefix the message with [agent_name]")
    send.set_defaults(func=cmd_send)

    tts_health_parser = subparsers.add_parser("tts-health", help="Check the local Kokoro TTS service")
    add_json_flag(tts_health_parser)
    tts_health_parser.set_defaults(func=cmd_tts_health)

    send_voice = subparsers.add_parser("send-voice", help="Send a Telegram voice message")
    add_json_flag(send_voice)
    send_voice.add_argument("--role", help="Role to attribute the message to")
    send_voice.add_argument("--agent-name", help="Override visible sender label")
    send_voice.add_argument("--chat-id", help="Override target chat id")
    send_voice.add_argument("--channel", help="Override logical channel")
    send_voice.add_argument("--message", help="Message text to synthesize")
    send_voice.add_argument("--stdin", action="store_true", help="Read or append message text from stdin")
    send_voice.add_argument("--silent", action="store_true", help="Send without notification sound")
    send_voice.add_argument("--raw", action="store_true", help="Do not prefix the spoken message with the agent label")
    send_voice.add_argument("--voice", help="Override Kokoro voice")
    send_voice.add_argument("--speed", type=float, help="Override Kokoro speech speed")
    send_voice.set_defaults(func=cmd_send_voice)

    send_photo = subparsers.add_parser("send-photo", help="Send a photo via Telegram")
    add_json_flag(send_photo)
    send_photo.add_argument("--role", help="Role to attribute to")
    send_photo.add_argument("--photo", required=True, help="Path to image file")
    send_photo.add_argument("--caption", default="", help="Photo caption")
    send_photo.set_defaults(func=cmd_send_photo)

    send_video = subparsers.add_parser("send-video", help="Send a video via Telegram")
    add_json_flag(send_video)
    send_video.add_argument("--role", help="Role to attribute to")
    send_video.add_argument("--video", required=True, help="Path to video file")
    send_video.add_argument("--caption", default="", help="Video caption")
    send_video.set_defaults(func=cmd_send_video)

    sync = subparsers.add_parser("sync", help="Sync inbound messages from Telegram")
    add_json_flag(sync)
    sync.add_argument("--channel", help="Override logical channel")
    sync.set_defaults(func=cmd_sync)

    latest = subparsers.add_parser("latest", help="Show the latest local message")
    add_json_flag(latest)
    latest.add_argument("--channel", help="Override logical channel")
    latest.add_argument("--direction", choices=["inbound", "outbound"], help="Filter by direction")
    latest.set_defaults(func=cmd_latest)

    history = subparsers.add_parser("history", help="Show local message history")
    add_json_flag(history)
    history.add_argument("--channel", help="Override logical channel")
    history.add_argument("--direction", choices=["inbound", "outbound"], help="Filter by direction")
    history.add_argument("--limit", type=int, default=10, help="Number of records to return")
    history.set_defaults(func=cmd_history)

    unread = subparsers.add_parser("unread", help="Show unread inbound messages")
    add_json_flag(unread)
    unread.add_argument("--channel", help="Override logical channel")
    unread.add_argument("--limit", type=int, default=10, help="Number of records to return")
    unread.set_defaults(func=cmd_unread)

    voice_status = subparsers.add_parser("voice-status", help="Show recent voice transcription status")
    add_json_flag(voice_status)
    voice_status.add_argument("--channel", help="Override logical channel")
    voice_status.add_argument("--limit", type=int, default=10, help="Number of records to inspect")
    voice_status.set_defaults(func=cmd_voice_status)

    mark_read = subparsers.add_parser("mark-read", help="Mark inbound messages as read")
    add_json_flag(mark_read)
    mark_read.add_argument("--channel", help="Override logical channel")
    mark_read.add_argument("--all", action="store_true", help="Mark all unread inbound messages as read")
    mark_read.add_argument("--message-id", help="Mark a single message id as read")
    mark_read.set_defaults(func=cmd_mark_read)

    enable = subparsers.add_parser("enable-session", help="Enable Telegram handling for a Claude session")
    add_json_flag(enable)
    enable.add_argument("--role", help="Role to assign to the session")
    enable.add_argument("--session-id", help="Explicit Claude session id")
    enable.add_argument("--tmux-session", help="tmux target session for notify/inject")
    enable.add_argument("--channel", help="Override logical channel for the managed poller")
    enable.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    enable.add_argument("--start-poller", action="store_true", help="Start or refresh a pinned background poller for this session")
    enable.add_argument("--poll-interval", type=int, default=15, help="Seconds between checks when starting a poller")
    enable.set_defaults(func=cmd_enable_session)

    disable = subparsers.add_parser("disable-session", help="Disable Telegram handling for a Claude session")
    add_json_flag(disable)
    disable.add_argument("--session-id", help="Explicit Claude session id")
    disable.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    disable.add_argument("--stop-poller", action="store_true", help="Stop the managed background poller if it is pinned to this session")
    disable.set_defaults(func=cmd_disable_session)

    session_status = subparsers.add_parser("session-status", help="Show Claude session registration state")
    add_json_flag(session_status)
    session_status.add_argument("--session-id", help="Explicit Claude session id")
    session_status.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    session_status.add_argument("--all", action="store_true", help="List all seen/registered sessions")
    session_status.set_defaults(func=cmd_session_status)

    hook = subparsers.add_parser("hook-check", help="Run a hook-triggered sync and delivery pass")
    add_json_flag(hook)
    hook.add_argument("--channel", help="Override logical channel")
    hook.add_argument("--session-id", help="Explicit Claude session id")
    hook.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    hook.add_argument("--stdin-hook", action="store_true", help="Read Claude hook payload JSON from stdin")
    hook.set_defaults(func=cmd_hook_check)

    poll = subparsers.add_parser("poll", help="Poll repeatedly using the hook-check flow")
    add_json_flag(poll)
    poll.add_argument("--channel", help="Override logical channel")
    poll.add_argument("--session-id", help="Explicit Claude session id")
    poll.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    poll.add_argument("--interval", type=int, default=15, help="Seconds between checks")
    poll.add_argument("--timeout", type=int, help="Stop after N seconds")
    poll.add_argument("--stdin-hook", action="store_true", help="Read one hook payload from stdin before polling")
    poll.set_defaults(func=cmd_poll)

    poller = subparsers.add_parser("poller", help="Manage the background Telegram poller")
    add_json_flag(poller)
    poller_sub = poller.add_subparsers(dest="poller_command", required=True)

    poller_start = poller_sub.add_parser("start", help="Start or refresh a pinned background poller")
    add_json_flag(poller_start)
    poller_start.add_argument("--channel", help="Override logical channel")
    poller_start.add_argument("--session-id", help="Explicit Claude session id")
    poller_start.add_argument("--use-latest-seen", action="store_true", help="Fall back to the most recently seen Claude session")
    poller_start.add_argument("--interval", type=int, default=15, help="Seconds between checks")
    poller_start.set_defaults(func=cmd_poller_start)

    poller_status = poller_sub.add_parser("status", help="Show the current background poller state")
    add_json_flag(poller_status)
    poller_status.set_defaults(func=cmd_poller_status)

    poller_stop = poller_sub.add_parser("stop", help="Stop the current background poller")
    add_json_flag(poller_stop)
    poller_stop.set_defaults(func=cmd_poller_stop)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
