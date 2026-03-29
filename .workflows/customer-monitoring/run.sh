#!/bin/bash
set -euo pipefail

# Resolve paths
WORKFLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$WORKFLOW_DIR/../.." && pwd)"

# Generate run ID: YYYYMMDD-HHMMSS-PID
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"

# Execute the workflow runner
exec python3 "$PROJECT_ROOT/tools/workflow_runner.py" \
  --workflow-dir "$WORKFLOW_DIR" \
  --project-root "$PROJECT_ROOT" \
  --run-id "$RUN_ID" \
  "$@"
