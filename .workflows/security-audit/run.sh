#!/bin/bash
set -euo pipefail

# Security Audit — Workflow Runner
# Dispatches a bounded supervisor+executor pair to run the security playbook.
# The pair self-terminates on completion; TTL kill is the safety net.

WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$WORKFLOW_DIR/../.." && pwd)"

DATE=$(date +%Y-%m-%d)
BRANCH="audit/security-${DATE}"
TTL_MINUTES=60

echo "[security-audit] Starting audit run: $DATE"
echo "[security-audit] Branch: $BRANCH"
echo "[security-audit] TTL: ${TTL_MINUTES}m"

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

echo "[security-audit] Completion monitor PID: $MONITOR_PID"
echo "[security-audit] Pair launched — supervisor will self-terminate on completion"

# The pair will:
# 1. Run the playbook (5 security checks)
# 2. Write report to .reports/security/$DATE.md
# 3. Add findings to backlog as proposed items (if any)
# 4. Commit and state "WORK COMPLETE"
# 5. Self-terminate (Layer 1) or be killed by completion monitor (Layer 2)
