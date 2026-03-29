#!/bin/bash
# wait_for_completion.sh — Monitor a bounded supervisor+executor pair for completion
# Usage: wait_for_completion.sh <sup_session> <exec_session> <timeout_minutes> [manifest_path] [observer_session]
#
# Polls every 30s for WORK COMPLETE in supervisor pane or manifest file.
# Kills both sessions (and optional observer session) on detection or timeout.

set -uo pipefail

SUP_SESSION="$1"
EXEC_SESSION="$2"
TIMEOUT_MINUTES="${3:-60}"
MANIFEST_PATH="${4:-}"
OBSERVER_SESSION="${5:-}"
POLL_INTERVAL=30

timeout_seconds=$((TIMEOUT_MINUTES * 60))
elapsed=0

log() { echo "[completion-monitor] $(date -u +%H:%M:%S) $*" >&2; }

kill_session() {
    local name="$1"
    if tmux has-session -t "$name" 2>/dev/null; then
        tmux kill-session -t "$name" 2>/dev/null && log "Killed: $name" || log "Already gone: $name"
    fi
}

log "Monitoring $SUP_SESSION + $EXEC_SESSION (TTL: ${TIMEOUT_MINUTES}m)"

while [ $elapsed -lt $timeout_seconds ]; do
    # Check if supervisor is still alive
    if ! tmux has-session -t "$SUP_SESSION" 2>/dev/null; then
        log "Supervisor self-terminated — cleaning up executor"
        kill_session "$EXEC_SESSION"
        if [ -n "$OBSERVER_SESSION" ]; then kill_session "$OBSERVER_SESSION"; fi
        exit 0
    fi

    # Check for WORK COMPLETE in supervisor pane (last 50 lines)
    pane_text=$(tmux capture-pane -t "$SUP_SESSION" -p -S -50 2>/dev/null || true)
    if echo "$pane_text" | grep -q "WORK COMPLETE"; then
        log "WORK COMPLETE detected in pane — killing sessions"
        kill_session "$EXEC_SESSION"
        sleep 5
        kill_session "$SUP_SESSION"
        if [ -n "$OBSERVER_SESSION" ]; then kill_session "$OBSERVER_SESSION"; fi
        exit 0
    fi

    # Check for completion manifest (forward-compat with BL-036)
    if [ -n "$MANIFEST_PATH" ] && [ -f "$MANIFEST_PATH" ]; then
        log "Completion manifest found at $MANIFEST_PATH — killing sessions"
        kill_session "$EXEC_SESSION"
        sleep 5
        kill_session "$SUP_SESSION"
        if [ -n "$OBSERVER_SESSION" ]; then kill_session "$OBSERVER_SESSION"; fi
        exit 0
    fi

    sleep $POLL_INTERVAL
    elapsed=$((elapsed + POLL_INTERVAL))
done

log "TTL expired (${TIMEOUT_MINUTES}m) — killing sessions"
kill_session "$EXEC_SESSION"
sleep 2
kill_session "$SUP_SESSION"
if [ -n "$OBSERVER_SESSION" ]; then kill_session "$OBSERVER_SESSION"; fi
exit 0
