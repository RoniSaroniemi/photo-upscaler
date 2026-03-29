#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENV=${KOKORO_TTS_VENV:-"$HOME/.local/share/agent-telegram/kokoro-venv"}
PYTHON="$VENV/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Missing Kokoro venv python at $PYTHON" >&2
  exit 1
fi

exec "$PYTHON" "$PROJECT_DIR/tools/kokoro_tts_service.py" "$@"
