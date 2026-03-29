#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
LOG_DIR="$PROJECT_DIR/state"
LOG_FILE="$LOG_DIR/cpo-codex-cron.log"
TMUX_BIN=${TMUX_BIN:-$(command -v tmux || echo /opt/homebrew/bin/tmux)}

mkdir -p "$LOG_DIR"

usage() {
  echo "Usage: $0 <main|subconscious> <session> [target_session]" >&2
  exit 1
}

[ "$#" -ge 2 ] || usage

MODE=$1
SESSION=$2
TARGET_SESSION=${3:-}

capture_tail() {
  "$TMUX_BIN" capture-pane -t "$1" -p -S -20 2>/dev/null || true
}

log() {
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$MODE" "$1" >>"$LOG_FILE"
}

TAIL_OUTPUT=$(capture_tail "$SESSION")
BOTTOM_LINES=$(printf '%s\n' "$TAIL_OUTPUT" | tail -n 8)

if [ -z "$TAIL_OUTPUT" ]; then
  log "skip: session '$SESSION' not readable"
  exit 0
fi

if printf '%s\n' "$BOTTOM_LINES" | grep -Eq 'Working \(|Determining|Running|esc to interrupt'; then
  log "skip: session '$SESSION' busy"
  exit 0
fi

if ! printf '%s\n' "$BOTTOM_LINES" | grep -Eq '^›|^❯|^>'; then
  log "skip: session '$SESSION' not at prompt"
  exit 0
fi

case "$MODE" in
  main)
    PROMPT="CPO-Codex recurring 30-minute check. Read .cpo/checks/check-30min.md and run one quick status cycle adapted to this framework-development repo. Review active supervisor/executor sessions, blockers, watchdog/comms state if relevant, and continue in-progress work rather than idling. If no concrete work is active, pick the highest-ROI non-overlapping support task around the live CPO."
    ;;
  subconscious)
    [ -n "$TARGET_SESSION" ] || usage
    PROMPT="Subconscious cycle. Base yourself on .cpo/subconsciousness-brief.md, but adapt it to the default tmux server and replace [CPO_TMUX_SESSION] with '$TARGET_SESSION'. Run exactly one monitoring cycle now: inspect the target session, inspect active sup-/exec- sessions, intervene on blocking dialogs if present, and send at most one short [subconscious] pulse only if it materially helps."
    ;;
  *)
    usage
    ;;
esac

"$TMUX_BIN" send-keys -t "$SESSION" -l -- "$PROMPT"
"$TMUX_BIN" send-keys -t "$SESSION" Enter
log "sent prompt to '$SESSION'"
