#!/bin/sh
# Convenience wrapper to run the Slack background poller.
# Usage: ./tools/run_slack_poller.sh [extra args]

set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

exec python3 "$PROJECT_DIR/tools/agent_slack.py" \
  --project-config "$PROJECT_DIR/.agent-comms/slack.json" \
  poll \
  --use-latest-seen \
  --interval 15 \
  "$@"
