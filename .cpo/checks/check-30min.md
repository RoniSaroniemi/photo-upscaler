# CPO 30-Minute Check — Quick Reference

*Read this file every time the 30-minute check fires. Do NOT expand scope beyond this list.*

---

## Autonomous Mode Standing Orders

When in fully autonomous mode (CEO away / overnight):
- **You CAN merge completed branches to main** without CEO approval (Phase 2+ work is pre-approved)
- **You CAN push to GitHub** after each merge — do this routinely to preserve progress
- **You CAN dispatch new briefs** from the queued backlog via the director
- **If blocked:** try multiple approaches. If all fail, work around the issue and continue other work. Do NOT stop.
- **These permissions are revoked** when the CEO explicitly says so. Until then, keep moving.

---

## 0. Lifecycle Gate Check (do this BEFORE anything else — 30 seconds)

```bash
head -6 .cpo/lifecycle.md 2>/dev/null
```

If lifecycle.md exists:
- **Current stage:** [read from file]
- **About to create or dispatch a brief?** → Verify it's within the current stage's allowed actions. If not, STOP.
- **Stage checklist complete?** → If yes and no CEO gate review has been requested, request one now (Telegram).
- **Expanding scope?** → Check the Verification-Before-Expansion checklist at the bottom of lifecycle.md. If any item is unchecked, verify first — run `/verify`.

This takes 30 seconds. If everything is aligned, proceed to the regular checks below.

---

## FIRST: Are You Mid-Task?

If you were autonomously executing work (dispatching projects, writing briefs, monitoring active work) before this cron fired, you MUST continue that work after the quick check. Do NOT let this cron interrupt your flow.

**After completing the 6 checks below:**
- If there is work in progress → continue executing it. Sequence your actions. Use `sleep N` to wait for short pending tasks (< 10 min) so you can follow up immediately.
- If you dispatched something to the director → sleep and check on it, don't wait 30 minutes.
- If you were writing a brief or document → go back and finish it.
- If nothing is in progress → end your turn, wait for next cron or CEO message.
- If the director is idle with no active projects → verify the director cancelled its own cron. If it didn't, tell it to. When dispatching new work to an idle director, remind it to restart its cron first.

**The 30-minute cron is a STATUS CHECK, not a work-stopper.** Your autonomous execution takes priority.

---

## What to Do (5 minutes max)

### 1. Director alive?
```bash
tmux -L $PROJECT_SLUG capture-pane -t director -p -S -10 | grep -v "^$" | tail -8
```
- If active output → good
- If dead/empty → restart: send handover prompt from `.director/handover-to-director.md`

### 2. Active projects status?
```bash
cat .director/registry.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{p[\"id\"]}: {p[\"status\"]} — {p.get(\"phase\",\"\")}') for p in d['projects'] if p['status']=='executing']"
```
- Note any status changes since last check
- If a project shows "complete" → flag for merge review (daily check handles the actual merge)

### 3. Is any supervisor idle but not cleaned up?

Supervisors that finish their work may sit idle at a prompt indefinitely. They do NOT self-terminate. This wastes a session and hides completion from you. **Detecting idle-but-done is critical.**

For each active supervisor session, run this check:
```bash
# 1. Is the prompt idle? (no spinner, no "thinking", just ❯)
tmux -L $PROJECT_SLUG capture-pane -t sup-<name> -p -S -3 | tail -3
# If you see just "❯" with no activity indicator → SUSPECT IDLE

# 2. Is the executor still alive? (if supervisor killed it → work is done)
tmux -L $PROJECT_SLUG has-session -t exec-<name> 2>&1
# "can't find session" = executor was killed = supervisor likely finished

# 3. Does evidence exist? (if evidence dir has files → work completed)
ls <worktree>/evidence/<project>/ 2>/dev/null | wc -l
# Files present = work was done

# 4. Look deeper — search for completion signals in supervisor history
tmux -L $PROJECT_SLUG capture-pane -t sup-<name> -p -S -40 | grep -iE "complete|done|all.*fixed|evidence|commit|PASS"
# Matches = supervisor finished but didn't exit
```

**If a supervisor is idle + executor dead + evidence exists → it's DONE.** Merge the work, kill the session, update status. Don't wait for the next cron cycle.

**The trap to avoid:** Only checking the last 5 lines of output. A finished supervisor looks identical to a working one if you don't check deep enough. Always verify with executor liveness + evidence existence.

### 4. PR Review & Merge

Check for open PRs created by supervisors:
```bash
gh pr list --state open
```

For each open PR:
```bash
# View PR details and CI status
gh pr view <number> --json title,state,statusCheckRollup,additions,deletions,headRefName

# Review the diff
gh pr diff <number>
```

**Merge decision (see `.cpo/policies/merge-policy.md` for full policy):**
- CI green (or no CI yet) + supervisor declared "WORK COMPLETE" + no critical path files → merge:
  ```bash
  gh pr merge <number> --merge --delete-branch
  ```
- Touches critical path files (`launch.py`, `CLAUDE.md`, `settings.json`, etc.) → review diff before merge
- CI failing → do NOT merge, supervisor must fix

### 5. Any escalations or blockers?
Scan director output for:
- `ESCALATE` / `blocked` / `STOP` / `human review` → intervene immediately
- `BUILD_REQUEST` / `RUNTIME_REQUEST` → director should handle, but verify it did
- Stall (same output as last check) → note it, intervene if 2nd consecutive stall

If a supervisor has shown the same output for 2+ consecutive 30-min checks:
- This is a stall, not slow progress
- Kill the pair and re-dispatch with remaining work
- Don't keep nudging — it makes the context worse

### 6. Telegram — Check Inbound + Conditional Send

**Step A — Check inbound messages:**
```bash
python3 tools/agent_telegram.py --project-config .agent-comms/telegram.json sync
python3 tools/agent_telegram.py --project-config .agent-comms/telegram.json unread --limit 5
```
If CEO sent a message → prioritize responding (in Telegram AND in session if they're active).

**Step B — If you need to send a message, check presence first:**
```bash
python3 tools/activitywatch_presence.py --json status
```

Use presence to decide HOW to communicate:

| Presence | CEO in this session? | Action |
|----------|---------------------|--------|
| `not-afk` (active) | YES, chatting with you | Don't Telegram — just respond in session |
| `not-afk` (active) | NO (at computer but elsewhere) | Telegram is a good time — they'll likely see it soon |
| `afk` | NO | Telegram is fine — message will be waiting when they return. Don't expect fast reply. |

**Step C — Choose text vs voice message:**

| Message type | Use text (`send`) | Use voice (`send-voice`) |
|-------------|-------------------|--------------------------|
| Short status (1-2 lines) | ✅ Text | Overkill |
| Blocker/decision ask | ✅ Text (scannable) | OK if context needed |
| Multi-point update (3+ items) | Too long to read | ✅ Voice — more natural to listen |
| Morning/midday/evening report | Too dense as text | ✅ Voice — CEO can listen while moving |
| Weekly summary | Both — text for reference | ✅ Voice as the primary delivery |

**Voice message command:**
```bash
python3 tools/agent_telegram.py --project-config .agent-comms/telegram.json send-voice --role CPO --message "Keep it conversational, concise, natural speech. No bullet points — speak in sentences."
```

**Key:** Voice messages should sound like a person giving a quick verbal update — not reading a document aloud. Keep it compact and fitting for speech.
| `afk` | — | Do NOT sleep-and-wait for a response. Continue other work. |

**Send a Telegram message ONLY if:**
- A NEW blocker appeared this cycle that needs CEO input (not a repeat of a known pending item)
- A project completed that the CEO was waiting on
- An escalation requires human action (permissions, environment failure)

**Do NOT send Telegram for:**
- Routine "all quiet" status — the CEO doesn't need to know nothing happened
- Repeat reminders of pending decisions — one notification is enough, don't nag
- Progress updates on running projects — those go in daily/shift reports
- Anything the CEO already knows from an active conversation

**If you send a message and need a response:**
- Check presence: if `not-afk` → sleep 5 minutes, check for reply
- If `afk` → don't wait, continue with other work. They'll reply when back.
- Do NOT send follow-up messages asking "did you see my message?"

**Mark messages as read after processing:**
```bash
python3 tools/agent_telegram.py --project-config .agent-comms/telegram.json mark-read --all
```

## 5. Short-Wait Follow-Ups

If during this check you took an action that should produce a result within minutes (e.g., restarted the director, sent a prompt to a supervisor, dispatched a merge), **don't wait 30 minutes for the next cron to verify it worked.** Instead:

**Use a sleep-then-check pattern:**
```bash
# Wait a few minutes, then verify
sleep 120 && tmux -L $PROJECT_SLUG capture-pane -t director -p -S -10 | grep -v "^$" | tail -8
```

**Guidelines:**
- Expecting a result in ~1 minute (e.g., director restart) → `sleep 60` then check
- Expecting a result in ~4 minutes (e.g., supervisor acknowledged a prompt) → `sleep 240` then check
- Expecting a result in ~10 minutes (e.g., a build or short task completing) → `sleep 600` then check
- If the follow-up check shows it's still not done → let it go, the next 30-minute cron will catch it
- **Max wait: 10 minutes.** If it's going to take longer than that, it's not a short-wait — let the regular cron handle it.

**Don't chain waits.** One sleep-then-check per action. If it's not done after the follow-up, move on.

---

## 6. Queue Health + Autonomous Investment

Check: is the execution queue getting short?

```
Active projects: [count from registry]
Queued briefs: [count waiting to be dispatched]
```

**If queue has ≤ 1 item remaining (approaching empty):**
1. Check `.cpo/autonomous-backlog.md` for pre-identified high-ROI investments
2. Start PREPARING the highest-priority backlog item (write brief, set up worktree)
3. If it's a quick POC/spot fix → dispatch directly to a supervisor+executor pair
4. If it's a multi-milestone investment → spin up a second director (you have authority for one additional director on demand)
5. Don't wait until the queue is EMPTY — start prepping when it's getting short

**If queue is empty AND no CEO work pending:**
- This is your autonomous investment time. You should NOT be idle.
- Work through the autonomous backlog in priority order
- Focus on: verification tooling, agent skills, process improvements, ideation backlog refill
- These investments compound — every hour spent here saves many hours later

**MANDATORY: If you have been idle for 2+ consecutive 30-min checks (1+ hour) with available backlog items, you MUST dispatch the next backlog item NOW.** Not "consider" dispatching — DISPATCH. Open the backlog, pick the top undone item, write the brief if needed, create the worktree, launch the supervisor+executor. Do it in this check cycle, not the next one. Idle with available work is a failure state — the overnight of 2026-03-23→24 proved that passive monitoring loops waste hours when the queue is empty but the backlog has work.

**Two-director model (when needed):**
- Director 1: the existing director running the CEO-approved sequential queue (e.g., Ferro Spike M1→M2→M3→M4)
- Director 2 (on demand): a second temporary director for autonomous investment work running in parallel
- You have CEO authority to spin up Director 2 when needed. It does NOT require approval.
- Director 2 should be killed when its work completes (disposable, same as all directors)

---

### 9. Backlog Integration
Run before reviewing the backlog to process any pending findings from agent runs:
```bash
python3 tools/backlog_integrator.py
```
This processes any pending findings files in `.cpo/findings/`. Review the output — it will list what was integrated (new items with assigned IDs). If no findings are pending, it reports nothing to process.

### 9.5 Verification-Between-Dispatches Check

**Did I verify before dispatching?** After any PR merge and before dispatching the next brief:
- Did I run the app? (Level 2: `npm run dev` + health check)
- Did I test the core flow? (Level 3: actual user journey)
- Did I check for anti-patterns? (`grep REPLACE_ME`, `grep TODO` in changed files)

**If I merged and immediately dispatched without verifying → STOP the pair and verify first.**
"Build passes" is Level 1. Level 1 is not sufficient between dispatches.

### 9.6 Role Boundary Self-Check

**Am I doing execution work?** Quick gut check:
- Am I writing code, building Docker, debugging errors, implementing features? → **STOP. Delegate.**
- Am I reading evidence, reviewing PRs, checking status, sending Telegram, dispatching pairs? → **Good. This is orchestration.**

**Rule:** If a task takes more than ~2 minutes of hands-on work, it should be a brief dispatched to a supervisor+executor pair. Even ad-hoc CEO requests should be delegated — write a quick brief, dispatch a pair, monitor the result. Your monitoring loop is more valuable than your coding.

### 10. Advisor Output
- Check: any new proposed items from the advisor?
```bash
python3 -c "import json; d=json.load(open('.cpo/backlog.json')); items=[e for e in d['entries'] if e.get('status')=='proposed']; [print(f'  {e[\"id\"]}: {e[\"title\"]} (P{e[\"priority\"][-1]}, {e.get(\"source\",\"?\")})')  for e in items] if items else print('  No proposed items')"
```
- If proposed items exist: review each one, promote actionable items to `backlog`, defer others with reason
- Check: advisor session alive?
```bash
tmux capture-pane -t advisor -p -S -5 2>/dev/null || echo "advisor session not running"
```
- If advisor is dead but should be running: restart with `python3 tools/launch.py --role advisor --direction .cpo/advisor/strategic-direction.md`

### 8. Watchdog Health
```bash
# Is the watchdog running?
python3 tools/session_watchdog.py --manifest config/session-manifest.json status
```
- If watchdog not running → restart it: `python3 tools/session_watchdog.py --manifest config/session-manifest.json start`
- If any session shows `failed_budget_exhausted` → investigate and fix the underlying issue, then `reset`
- If orphan count is high (>5) → check if the director is cleaning up properly

---

## What NOT to Do
- Don't review effect quality (that's weekly)
- Don't generate ideas UNLESS the candidate backlog is empty AND queue is short (then it's justified)
- Don't merge completed work without checking PR status first (see step 4)
- Don't update the roadmap (that's daily)

## 7. Workflow Escalations

```bash
ls .cpo/escalations/workflow-*.md 2>/dev/null | head -5
```
- If escalation files exist → read the escalation, understand what failed
- Handle the failed workflow decision (manually decide, fix the prompt, or re-run)
- Delete the escalation file after handling

---

## Files You May Need
- `.director/registry.json` — project states
- `.director/handover-to-director.md` — if director needs restart
- `.cpo/roadmap.md` — only if CEO asks about status
- `.workflows/registry.json` — workflow health (if workflows are configured)
