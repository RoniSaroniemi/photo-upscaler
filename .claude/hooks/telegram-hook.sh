#!/bin/sh
# Telegram session hook — fires on SessionStart and Stop.
# Exits silently if Telegram is not yet configured (placeholder values in config).

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CONFIG="$PROJECT_DIR/.agent-comms/telegram.json"

# Skip if config doesn't exist or still has placeholder values
if [ ! -f "$CONFIG" ]; then
  exit 0
fi
if grep -q "REPLACE_WITH" "$CONFIG" 2>/dev/null; then
  exit 0
fi

exec python3 "$PROJECT_DIR/tools/agent_telegram.py" \
  --project-config "$CONFIG" \
  hook-check \
  --stdin-hook
