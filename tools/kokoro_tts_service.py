#!/usr/bin/env python3
"""
Warm localhost Kokoro TTS service for outbound Telegram voice notes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
DEFAULT_SESSION_TOKEN = "kokoro-local-dev-token"
DEFAULT_MODEL_DIR = Path.home() / ".local" / "share" / "agent-telegram" / "kokoro-models"
DEFAULT_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
DEFAULT_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "kokoro-v1.0.onnx"
DEFAULT_VOICES_PATH = DEFAULT_MODEL_DIR / "voices-v1.0.bin"
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.25
DEFAULT_LANGUAGE = "en-us"


try:
    import soundfile as sf
    from kokoro_onnx import Kokoro
except ImportError as exc:  # pragma: no cover - surfaced to operator
    raise SystemExit(
        "Missing Kokoro runtime dependencies. Install them in the dedicated venv before starting the service."
    ) from exc


def log(message: str) -> None:
    sys.stderr.write(f"[kokoro-tts] {message}\n")
    sys.stderr.flush()


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


class KokoroRuntime:
    def __init__(
        self,
        *,
        model_path: Path,
        voices_path: Path,
        model_url: str,
        voices_url: str,
        default_voice: str,
        default_speed: float,
        default_language: str,
    ) -> None:
        self.model_path = model_path
        self.voices_path = voices_path
        self.model_url = model_url
        self.voices_url = voices_url
        self.default_voice = default_voice
        self.default_speed = default_speed
        self.default_language = default_language
        self._kokoro: Kokoro | None = None
        self._voices: set[str] = set()
        self._lock = threading.Lock()
        self._ready = False
        self._last_error: str | None = None

    def bootstrap(self) -> None:
        with self._lock:
            try:
                if not self.model_path.exists():
                    log(f"downloading model to {self.model_path}")
                    download_file(self.model_url, self.model_path)
                if not self.voices_path.exists():
                    log(f"downloading voices to {self.voices_path}")
                    download_file(self.voices_url, self.voices_path)
                self._kokoro = Kokoro(str(self.model_path), str(self.voices_path))
                self._voices = set(self._kokoro.get_voices())
                if self.default_voice not in self._voices:
                    raise RuntimeError(f"default voice {self.default_voice!r} not found")
                self._ready = True
                self._last_error = None
                log(f"ready voice={self.default_voice} language={self.default_language} voices={len(self._voices)}")
            except Exception as exc:  # pragma: no cover - depends on runtime state
                self._ready = False
                self._last_error = str(exc)
                log(f"bootstrap failed: {exc}")

    def health(self) -> dict[str, Any]:
        return {
            "ok": self._ready,
            "ready": self._ready,
            "voice": self.default_voice,
            "speed": self.default_speed,
            "language": self.default_language,
            "voices_count": len(self._voices),
            "error": self._last_error,
        }

    def synthesize(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not self._ready or self._kokoro is None:
            return HTTPStatus.SERVICE_UNAVAILABLE, {
                "ok": False,
                "ready": False,
                "error": self._last_error or "kokoro_not_ready",
            }

        text = str(payload.get("text") or "").strip()
        if not text:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "text_required"}

        voice = str(payload.get("voice") or self.default_voice)
        if voice not in self._voices:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"unknown_voice:{voice}"}

        try:
            speed = float(payload.get("speed") or self.default_speed)
        except (TypeError, ValueError):
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_speed"}
        if speed < 0.5 or speed > 2.0:
            return HTTPStatus.BAD_REQUEST, {"ok": False, "error": "speed_out_of_range"}

        language = str(payload.get("language") or self.default_language)

        try:
            samples, sample_rate = self._kokoro.create(text, voice=voice, speed=speed, lang=language)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as handle:
                output_path = Path(handle.name)
            sf.write(str(output_path), samples, sample_rate)
            duration_seconds = float(len(samples) / sample_rate) if sample_rate else 0.0
            return HTTPStatus.OK, {
                "ok": True,
                "audio_path": str(output_path),
                "voice": voice,
                "speed": speed,
                "language": language,
                "duration_seconds": round(duration_seconds, 4),
                "sample_rate_hz": sample_rate,
                "error": None,
            }
        except Exception as exc:  # pragma: no cover - depends on runtime state
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    server_version = "KokoroTTS/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        log(format % args)

    @property
    def runtime(self) -> KokoroRuntime:
        return self.server.runtime  # type: ignore[attr-defined]

    @property
    def session_token(self) -> str:
        return self.server.session_token  # type: ignore[attr-defined]

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authenticate(self) -> bool:
        token = self.headers.get("X-Kokoro-Session-Token", "")
        if token != self.session_token:
            self._json_response(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        if self.path != "/v1/tts/health":
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authenticate():
            return
        health = self.runtime.health()
        self._json_response(HTTPStatus.OK if health.get("ok") else HTTPStatus.SERVICE_UNAVAILABLE, health)

    def do_POST(self) -> None:
        if self.path != "/v1/tts/speak":
            self._json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authenticate():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_content_length"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "payload_must_be_object"})
            return
        status, response = self.runtime.synthesize(payload)
        self._json_response(status, response)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Warm local Kokoro TTS service")
    parser.add_argument("--host", default=os.environ.get("KOKORO_TTS_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("KOKORO_TTS_PORT", str(DEFAULT_PORT))))
    parser.add_argument(
        "--session-token",
        default=os.environ.get("KOKORO_TTS_SESSION_TOKEN", DEFAULT_SESSION_TOKEN),
    )
    parser.add_argument("--model-path", default=os.environ.get("KOKORO_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
    parser.add_argument("--voices-path", default=os.environ.get("KOKORO_VOICES_PATH", str(DEFAULT_VOICES_PATH)))
    parser.add_argument("--model-url", default=os.environ.get("KOKORO_MODEL_URL", DEFAULT_MODEL_URL))
    parser.add_argument("--voices-url", default=os.environ.get("KOKORO_VOICES_URL", DEFAULT_VOICES_URL))
    parser.add_argument("--default-voice", default=os.environ.get("KOKORO_DEFAULT_VOICE", DEFAULT_VOICE))
    parser.add_argument("--default-speed", type=float, default=float(os.environ.get("KOKORO_DEFAULT_SPEED", str(DEFAULT_SPEED))))
    parser.add_argument("--default-language", default=os.environ.get("KOKORO_DEFAULT_LANGUAGE", DEFAULT_LANGUAGE))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime = KokoroRuntime(
        model_path=Path(args.model_path).expanduser(),
        voices_path=Path(args.voices_path).expanduser(),
        model_url=str(args.model_url),
        voices_url=str(args.voices_url),
        default_voice=str(args.default_voice),
        default_speed=float(args.default_speed),
        default_language=str(args.default_language),
    )
    runtime.bootstrap()
    server = ThreadingHTTPServer((str(args.host), int(args.port)), Handler)
    server.runtime = runtime  # type: ignore[attr-defined]
    server.session_token = str(args.session_token)  # type: ignore[attr-defined]
    log(f"listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
