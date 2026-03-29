#!/bin/bash
# Test the orchestration framework structure
# Verifies: all files present, no leaked project-specific references, valid JSON, stdlib-only Python
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Claude Orchestration Framework — Structure Test ==="
echo "Root: $REPO_ROOT"
echo ""

PASS=0
FAIL=0

check() {
  local label="$1"
  local result="$2"
  if [ "$result" = "ok" ]; then
    printf "  \033[0;32mPASS\033[0m  %s\n" "$label"
    PASS=$((PASS + 1))
  else
    printf "  \033[0;31mFAIL\033[0m  %s — %s\n" "$label" "$result"
    FAIL=$((FAIL + 1))
  fi
}

# --- File presence checks ---
echo "--- File Presence ---"

EXPECTED_FILES=(
  "setup.sh"
  "CLAUDE.md"
  "README.md"
  ".gitignore"
  ".orchestration/setup-brief.md"
  ".orchestration/setup-feedback.md"
  ".orchestration/project-types.md"
  ".cpo/cpo-routine.md"
  ".cpo/decision-framework.md"
  ".cpo/capacity.md"
  ".cpo/subconsciousness-brief.md"
  ".cpo/autonomous-backlog.md"
  ".cpo/daily-todo.md"
  ".cpo/checks/check-30min.md"
  ".cpo/checks/check-6hour.md"
  ".cpo/checks/check-daily.md"
  ".cpo/checks/check-weekly.md"
  ".cpo/checks/cron-prompts.md"
  ".cpo/templates/brief-template.md"
  ".cpo/templates/recovery-brief-cpo.md"
  ".cpo/templates/recovery-brief-subconscious.md"
  ".director/director-instructions.md"
  ".director/registry.json"
  ".director/handover-to-director.md"
  ".claude/settings.json"
  ".claude/hooks/telegram-hook.sh"
  ".claude/skills/telegram-enable-communications/SKILL.md"
  ".claude/skills/telegram-send-message/SKILL.md"
  ".claude/skills/telegram-read-messages/SKILL.md"
  ".claude/skills/telegram-send-voice-message/SKILL.md"
  ".claude/skills/telegram-send-photo/SKILL.md"
  ".claude/skills/telegram-send-video/SKILL.md"
  ".claude/skills/activitywatch-user-presence/SKILL.md"
  ".agent-comms/telegram.json.example"
  ".agent-comms/slack.json.example"
  ".agent-comms/routing.json.example"
  "tools/agent_telegram.py"
  "tools/agent_slack.py"
  "tools/agent_dispatcher.py"
  "tools/workflow_runner.py"
  "tools/workflow_scheduler.py"
  "tools/activitywatch_presence.py"
  "tools/session_watchdog.py"
  "tools/central_router.py"
  "tools/pid_lock.py"
  "tools/orch.py"
  "tools/skill_library.py"
  "tools/delegate.py"
  "tools/launch.py"
  "tools/agent_registry.py"
  "tools/metrics_report.py"
  "tools/codex_tick.py"
  "config/session-manifest.json.example"
  "tools/run_telegram_poller.sh"
  "tools/run_slack_poller.sh"
  ".claude/hooks/slack-hook.sh"
  ".claude/skills/slack-enable-communications/SKILL.md"
  ".claude/skills/slack-send-message/SKILL.md"
  ".claude/skills/slack-read-messages/SKILL.md"
  ".claude/skills/slack-send-file/SKILL.md"
  ".claude/skills/skill-library/SKILL.md"
  ".claude/skills/delegate/SKILL.md"
  ".claude/skills/verify/SKILL.md"
  ".workflows/registry.json"
  ".workflows/workflow-template/workflow.json"
  ".workflows/workflow-template/run.sh"
  ".workflows/workflow-template/WORKFLOW.md"
  "docs/telegram-agent-gateway.md"
  "docs/slack-agent-gateway.md"
  "docs/activitywatch-user-presence.md"
  "tools/queue_runner.py"
  "tools/queue_daemon.py"
  ".operations/queue-template/queue.json"
  ".operations/tori-scanner/queue.json"
  ".operations/tori-scanner/seed-urls.txt"
  ".operations/tori-scanner/executor-prompt.md"
  ".operations/tori-scanner/queue-director-handover.md"
  "tools/panel_runner.py"
  ".cpo/checks/when-to-panel.md"
  ".cpo/templates/panel-output-format.md"
  ".cpo/templates/persona-prompts/README.md"
  ".cpo/templates/persona-prompts/moonshot-thinker.md"
  ".cpo/templates/persona-prompts/speed-builder.md"
  ".cpo/templates/persona-prompts/compounding-strategist.md"
  ".cpo/templates/persona-prompts/risk-analyst.md"
  ".cpo/templates/persona-prompts/user-advocate.md"
  ".cpo/templates/persona-prompts/technical-architect.md"
  ".cpo/templates/persona-prompts/business-analyst.md"
  ".cpo/templates/planning-brief.md"
  ".cpo/templates/project-envelope.md"
  ".cpo/advisor/advisor-instructions.md"
  ".cpo/advisor/strategic-direction-template.md"
  ".cpo/advisor/bottleneck-analysis.md"
  ".cpo/advisor/gap-analysis.md"
  ".cpo/advisor/landscape.md"
  ".cpo/advisor/cycle-log.md"
  ".cpo/advisor/exploration-log.md"
)

for f in "${EXPECTED_FILES[@]}"; do
  if [ -f "$REPO_ROOT/$f" ]; then
    check "$f" "ok"
  else
    check "$f" "MISSING"
  fi
done

# --- Leaked references ---
echo ""
echo "--- Leaked References ---"

# Check for metal-dust references (excluding README which may mention origin)
LEAKS=$(grep -rl "metal-dust\|Metal Dust\|MetalParticle" "$REPO_ROOT" \
  --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
  2>/dev/null | grep -v ".git/" | grep -v "README.md" | grep -v "test-setup.sh" || true)

if [ -z "$LEAKS" ]; then
  check "No metal-dust references" "ok"
else
  check "No metal-dust references" "Found in: $(echo "$LEAKS" | tr '\n' ' ')"
fi

# Check for hardcoded user paths
USERLEAKS=$(grep -rl "/Users/roni" "$REPO_ROOT" \
  --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
  2>/dev/null | grep -v ".git/" | grep -v "test-setup.sh" || true)

if [ -z "$USERLEAKS" ]; then
  check "No hardcoded user paths" "ok"
else
  check "No hardcoded user paths" "Found in: $(echo "$USERLEAKS" | tr '\n' ' ')"
fi

# --- JSON validity ---
echo ""
echo "--- JSON Validity ---"

for json_file in ".director/registry.json" ".agent-comms/telegram.json.example" ".agent-comms/slack.json.example" ".agent-comms/routing.json.example" ".claude/settings.json" ".workflows/registry.json" ".workflows/workflow-template/workflow.json" ".workflows/customer-monitoring/workflow.json" "config/session-manifest.json.example" ".operations/queue-template/queue.json" ".operations/tori-scanner/queue.json"; do
  if python3 -c "import json; json.load(open('$REPO_ROOT/$json_file'))" 2>/dev/null; then
    check "$json_file valid JSON" "ok"
  else
    check "$json_file valid JSON" "INVALID"
  fi
done

# Director registry should have empty projects
PROJECTS=$(python3 -c "import json; d=json.load(open('$REPO_ROOT/.director/registry.json')); print(len(d['projects']))" 2>/dev/null)
if [ "$PROJECTS" = "0" ]; then
  check "director registry.json has 0 projects" "ok"
else
  check "director registry.json has 0 projects" "has $PROJECTS"
fi

# Workflow registry should have empty or placeholder workflows
WF_VALID=$(python3 -c "import json; d=json.load(open('$REPO_ROOT/.workflows/registry.json')); print('ok' if 'workflows' in d else 'missing workflows key')" 2>/dev/null || echo "INVALID")
check "workflow registry.json structure" "$WF_VALID"

# --- Python stdlib check ---
echo ""
echo "--- Python Stdlib Only ---"

for py in tools/agent_telegram.py tools/agent_slack.py tools/agent_dispatcher.py tools/workflow_runner.py tools/workflow_scheduler.py tools/activitywatch_presence.py tools/session_watchdog.py tools/central_router.py tools/pid_lock.py tools/orch.py tools/skill_library.py tools/delegate.py tools/launch.py tools/agent_registry.py tools/metrics_report.py tools/codex_tick.py tools/queue_runner.py tools/queue_daemon.py tools/panel_runner.py; do
  EXTERNAL=$(python3 -c "
import ast, sys
with open('$REPO_ROOT/$py') as f:
    tree = ast.parse(f.read())
stdlib = set(sys.stdlib_module_names)
found = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split('.')[0] not in stdlib:
                found.append(alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module:
        if node.module.split('.')[0] not in stdlib and node.module != '__future__':
            found.append(node.module)
if found:
    print(','.join(found))
" 2>/dev/null || echo "CHECK_FAILED")
  if [ -z "$EXTERNAL" ]; then
    check "$py stdlib-only" "ok"
  else
    check "$py stdlib-only" "non-stdlib: $EXTERNAL"
  fi
done

# --- Executable checks ---
echo ""
echo "--- Executables ---"

for script in setup.sh .claude/hooks/telegram-hook.sh .claude/hooks/slack-hook.sh tools/run_telegram_poller.sh tools/run_slack_poller.sh; do
  if [ -x "$REPO_ROOT/$script" ]; then
    check "$script executable" "ok"
  else
    check "$script executable" "NOT EXECUTABLE"
  fi
done

# --- Queue Runner Functional Tests ---
echo ""
echo "--- Queue Runner ---"

QUEUE_TEST_DIR=$(mktemp -d)
QUEUE_TEST_CONFIG="$QUEUE_TEST_DIR/queue.json"
cat > "$QUEUE_TEST_CONFIG" <<'QEOF'
{
  "queue_id": "test-queue",
  "name": "Test Queue",
  "description": "Functional test queue",
  "status": "active",
  "created_at": "2026-01-01"
}
QEOF

# init
INIT_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" init --config "$QUEUE_TEST_CONFIG" 2>&1)
if [ -f "$QUEUE_TEST_DIR/queue.db" ]; then
  check "queue init creates DB" "ok"
else
  check "queue init creates DB" "no queue.db"
fi

# add 5 items
for i in 1 2 3 4 5; do
  python3 "$REPO_ROOT/tools/queue_runner.py" add --config "$QUEUE_TEST_CONFIG" --url "https://example.com/$i" >/dev/null 2>&1
done
STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "ready=5"; then
  check "add 5 items → ready=5" "ok"
else
  check "add 5 items → ready=5" "got: $STATUS_OUT"
fi

# claim 2
CLAIM1=$(python3 "$REPO_ROOT/tools/queue_runner.py" claim --config "$QUEUE_TEST_CONFIG" --worker-id w1 --json 2>&1)
CLAIM2=$(python3 "$REPO_ROOT/tools/queue_runner.py" claim --config "$QUEUE_TEST_CONFIG" --worker-id w2 --json 2>&1)
ID1=$(echo "$CLAIM1" | python3 -c "import sys,json; print(json.load(sys.stdin)['item_id'])" 2>/dev/null)
ID2=$(echo "$CLAIM2" | python3 -c "import sys,json; print(json.load(sys.stdin)['item_id'])" 2>/dev/null)
if [ -n "$ID1" ] && [ -n "$ID2" ] && [ "$ID1" != "$ID2" ]; then
  check "two claims → two different items" "ok"
else
  check "two claims → two different items" "id1=$ID1 id2=$ID2"
fi

STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "ready=3" && echo "$STATUS_OUT" | grep -q "claimed=2"; then
  check "status after claims: ready=3, claimed=2" "ok"
else
  check "status after claims: ready=3, claimed=2" "got: $STATUS_OUT"
fi

# complete one
python3 "$REPO_ROOT/tools/queue_runner.py" complete --config "$QUEUE_TEST_CONFIG" --item-id "$ID1" --artifact-path "artifacts/$ID1.json" >/dev/null 2>&1
STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "completed=1"; then
  check "complete → completed=1" "ok"
else
  check "complete → completed=1" "got: $STATUS_OUT"
fi

# fail one
python3 "$REPO_ROOT/tools/queue_runner.py" fail --config "$QUEUE_TEST_CONFIG" --item-id "$ID2" --error "test error" >/dev/null 2>&1
STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "failed=1"; then
  check "fail → failed=1" "ok"
else
  check "fail → failed=1" "got: $STATUS_OUT"
fi

# retry
python3 "$REPO_ROOT/tools/queue_runner.py" retry --config "$QUEUE_TEST_CONFIG" --item-id "$ID2" >/dev/null 2>&1
STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "ready=4" && echo "$STATUS_OUT" | grep -q "failed=0"; then
  check "retry → item back to ready" "ok"
else
  check "retry → item back to ready" "got: $STATUS_OUT"
fi

# batch add
python3 "$REPO_ROOT/tools/queue_runner.py" add --config "$QUEUE_TEST_CONFIG" --batch-file "$REPO_ROOT/.operations/tori-scanner/seed-urls.txt" >/dev/null 2>&1
STATUS_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" status --config "$QUEUE_TEST_CONFIG" 2>&1)
if echo "$STATUS_OUT" | grep -q "total=20"; then
  check "batch add 15 URLs → total=20" "ok"
else
  check "batch add 15 URLs → total=20" "got: $STATUS_OUT"
fi

# list --json
LIST_OUT=$(python3 "$REPO_ROOT/tools/queue_runner.py" list --config "$QUEUE_TEST_CONFIG" --status ready --limit 3 --json 2>&1)
LIST_COUNT=$(echo "$LIST_OUT" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
if [ "$LIST_COUNT" = "3" ]; then
  check "list --status ready --limit 3 → 3 items" "ok"
else
  check "list --status ready --limit 3 → 3 items" "got $LIST_COUNT"
fi

# cleanup
rm -rf "$QUEUE_TEST_DIR"

# --- Queue Daemon ---
echo ""
echo "--- Queue Daemon ---"

DAEMON_TEST_DIR=$(mktemp -d)
DAEMON_TEST_CONFIG="$DAEMON_TEST_DIR/queue.json"
cat > "$DAEMON_TEST_CONFIG" <<'DEOF'
{
  "queue_id": "daemon-test",
  "name": "Daemon Test Queue",
  "description": "Functional test for queue daemon",
  "status": "active",
  "created_at": "2026-01-01",
  "concurrency": {
    "max_workers": 2,
    "worker_provider": "codex",
    "worker_timeout_minutes": 1
  },
  "budget": {
    "max_items_per_day": 100
  },
  "daemon": {
    "poll_interval_seconds": 2,
    "mode": "passive",
    "director_review_interval": 50,
    "director_session": "director"
  }
}
DEOF

# Init the test queue DB
python3 "$REPO_ROOT/tools/queue_runner.py" init --config "$DAEMON_TEST_CONFIG" >/dev/null 2>&1

# Start daemon in background — it will poll empty queue
python3 "$REPO_ROOT/tools/queue_daemon.py" --config "$DAEMON_TEST_CONFIG" run &
DAEMON_PID=$!
sleep 3

# Check daemon wrote status file
if [ -f "$REPO_ROOT/state/daemon-status.json" ]; then
  DSTATUS=$(python3 -c "import json; d=json.load(open('$REPO_ROOT/state/daemon-status.json')); print(d.get('running', False))" 2>/dev/null)
  if [ "$DSTATUS" = "True" ]; then
    check "daemon writes status file (running=True)" "ok"
  else
    check "daemon writes status file (running=True)" "running=$DSTATUS"
  fi
else
  check "daemon writes status file (running=True)" "no status file"
fi

# Check PID lock exists
DAEMON_LOCK="$REPO_ROOT/state/daemon-daemon-test.lock"
if [ -f "$DAEMON_LOCK" ]; then
  LOCK_PID=$(cat "$DAEMON_LOCK")
  if [ "$LOCK_PID" = "$DAEMON_PID" ]; then
    check "PID lock contains correct PID" "ok"
  else
    check "PID lock contains correct PID" "expected=$DAEMON_PID got=$LOCK_PID"
  fi
else
  check "PID lock contains correct PID" "no lock file"
fi

# Check duplicate daemon is rejected
DUPE_OUT=$(python3 "$REPO_ROOT/tools/queue_daemon.py" --config "$DAEMON_TEST_CONFIG" run 2>&1 &
  DUPE_PID=$!; sleep 2; kill $DUPE_PID 2>/dev/null; wait $DUPE_PID 2>/dev/null; echo $?)
if echo "$DUPE_OUT" | grep -qi "already running\|lock"; then
  check "PID lock prevents duplicate daemons" "ok"
else
  check "PID lock prevents duplicate daemons" "no lock rejection detected"
fi

# Check status command works
STATUS_CMD_OUT=$(python3 "$REPO_ROOT/tools/queue_daemon.py" status 2>&1)
if echo "$STATUS_CMD_OUT" | grep -q '"queue_id"'; then
  check "daemon status command returns JSON" "ok"
else
  check "daemon status command returns JSON" "unexpected output"
fi

# Check mode in status
MODE_VAL=$(python3 -c "import json; d=json.load(open('$REPO_ROOT/state/daemon-status.json')); print(d.get('mode',''))" 2>/dev/null)
if [ "$MODE_VAL" = "passive" ]; then
  check "daemon mode is passive" "ok"
else
  check "daemon mode is passive" "got: $MODE_VAL"
fi

# Stop the daemon gracefully
kill "$DAEMON_PID" 2>/dev/null
wait "$DAEMON_PID" 2>/dev/null

# Verify daemon stopped and cleaned up lock
sleep 1
if [ ! -f "$DAEMON_LOCK" ]; then
  check "daemon cleans up lock on stop" "ok"
else
  check "daemon cleans up lock on stop" "lock still exists"
fi

# cleanup
rm -rf "$DAEMON_TEST_DIR"
rm -f "$REPO_ROOT/state/daemon-status.json" "$REPO_ROOT/state/daemon-status.tmp"

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
