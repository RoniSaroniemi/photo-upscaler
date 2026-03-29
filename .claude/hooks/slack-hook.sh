#!/bin/sh
# Slack hook — fires on SessionStart/Stop to sync and deliver Slack messages.
# Mirrors telegram-hook.sh. Exits silently if Slack is not configured.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CONFIG="$PROJECT_DIR/.agent-comms/slack.json"

# Skip if config doesn't exist
if [ ! -f "$CONFIG" ]; then
  exit 0
fi

# Skip if config still has placeholder values
if grep -q "REPLACE_WITH" "$CONFIG" 2>/dev/null; then
  exit 0
fi

exec python3 "$PROJECT_DIR/tools/agent_slack.py" \
  --project-config "$CONFIG" \
  hook-check \
  --stdin-hook
