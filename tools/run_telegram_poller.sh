#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

exec python3 "$PROJECT_DIR/tools/agent_telegram.py" \
  --project-config "$PROJECT_DIR/.agent-comms/telegram.json" \
  poll \
  --use-latest-seen \
  --interval 15 \
  "$@"
