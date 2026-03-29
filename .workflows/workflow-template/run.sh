#!/bin/bash
set -euo pipefail

# [Workflow Name] — Workflow Runner
# Dispatches a bounded supervisor+executor pair to run the workflow playbook.
# The pair self-terminates on completion; the completion monitor is the safety net.

# Resolve paths
WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$WORKFLOW_DIR/../.." && pwd)"

# Generate run ID: YYYYMMDD-HHMMSS-PID
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
DATE=$(date +%Y-%m-%d)
BRANCH="workflow/template-${DATE}"
TTL_MINUTES=60

echo "[workflow] Starting run: $RUN_ID"
echo "[workflow] Branch: $BRANCH"
echo "[workflow] TTL: ${TTL_MINUTES}m"

# Launch the supervisor+executor pair
python3 "$PROJECT_ROOT/tools/launch.py" --role pair \
  --brief "$WORKFLOW_DIR/playbook.md" \
  --branch "$BRANCH" \
  --provider claude

# Derive session names (matches launch.py convention)
SESSION_BASE=$(echo "$BRANCH" | sed 's|/|-|g')
SUP_SESSION="sup-${SESSION_BASE}"
EXEC_SESSION="exec-${SESSION_BASE}"

# Completion monitor: kills both sessions on WORK COMPLETE or TTL expiry
"$WORKFLOW_DIR/../lib/wait_for_completion.sh" \
    "$SUP_SESSION" "$EXEC_SESSION" "$TTL_MINUTES" &
MONITOR_PID=$!

echo "[workflow] Completion monitor PID: $MONITOR_PID"
echo "[workflow] Pair launched — supervisor will self-terminate on completion"
