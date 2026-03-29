# Supervisor Brief — [Title]

**Branch:** `feature/[name]`
**Executor session:** `[session-name]`

<!--
  SUPERVISOR BRIEF TEMPLATE
  =========================
  This brief is the complete instruction set for an executor agent working on a
  specific task. The executor should be able to complete the work using only this
  document — no additional context should be required.

  How to use:
  1. Replace [Title] with a concise description of the task.
  2. Set the branch name and executor session identifier.
  3. Fill every section with enough detail that the executor never needs to ask
     clarifying questions.
  4. Implementation Phases should be ordered and specific — include file paths,
     function names, and exact changes where possible.
  5. Verification must include exact commands the executor will run to confirm
     the work is correct.
  6. The "Does NOT Include" section prevents scope creep — list anything the
     executor might be tempted to do but should not.
-->

## 1. The Problem

<!--
  Describe what is broken, missing, or suboptimal and why it matters.
  Include:
  - Current behavior vs expected behavior
  - Who or what is affected
  - Why this needs to be fixed now
-->

## 2. The Solution

<!--
  Describe what will be built or changed at a high level.
  Include:
  - The approach and key design decisions
  - Which parts of the codebase are involved
  - Expected end state after the work is complete
-->

## 3. Implementation Phases

<!--
  Break the work into sequential phases. Each phase should be independently
  committable. Include specific file paths, function names, and change descriptions.
-->

### Phase 1: [Phase Title]

1.
2.
3.

### Phase 2: [Phase Title]

1.
2.
3.

### Phase 3: [Phase Title]

1.
2.
3.

## 4. Verification

<!--
  List the exact commands the executor must run to verify the work is correct.
  These should be copy-pasteable. Include expected output where helpful.
  Examples: test commands, linting, build commands, curl requests.
-->

```bash
# Verification commands go here
```

## 5. What This Does NOT Include

<!--
  Explicitly list things that are out of scope for this task.
  This prevents the executor from expanding scope or making unnecessary changes.
  Be specific: "Do not refactor X", "Do not update Y", "Tests for Z are separate".
-->

-

---

## If Your Executor Stalls

If the executor repeats the same actions for 10+ minutes without progress:
- Kill the executor: tmux kill-session -t <executor>
- Create a fresh executor session and relaunch
- Re-send only the remaining work, not the full brief
- Don't keep steering a confused agent — replace it

---

## Backlog Proposals

If your executor identifies items worth adding to the project backlog (bugs found, improvements, follow-up work), write them to a findings file in the **main repo**:

1. Get main repo path: `python3 -c "import subprocess; print(subprocess.check_output(['git','worktree','list','--porcelain']).decode().split('\n')[0].replace('worktree ',''))"`
2. Write findings to: `<MAIN_REPO_PATH>/.cpo/findings/<run-id>-<source>.json`
   - `run_id`: use format `YYYYMMDD-HHMMSS-<6-char-random>`
   - `source`: your role name (e.g., `security`, `advisor`, `executor`)
3. Schema: see `.cpo/findings/SCHEMA.md`

**NEVER write directly to backlog.json. The CPO integrates findings during 30-min checks.**

---

**IMPORTANT: When all phases are complete and all verification passes:**

1. Push your branch and create a PR:
```bash
git push origin <branch>
gh pr create --title "BL-NNN: <title>" --body "$(cat <<'EOF'
## Summary
<description of what was done>

## Verification
<what was tested and results>
EOF
)" --base main --head <branch>
```
2. Your final message must be: **WORK COMPLETE — PR created, ready for review**
3. Self-terminate by running: `tmux kill-session -t $(tmux display-message -p '#S')`
   This kills the current supervisor session. The executor was already killed by you earlier.
   There is nothing after this step — the session ends.

> **Note:** If running in a workflow context, the run.sh completion monitor will also kill the session — self-termination is belt-and-suspenders.

## Monitoring Your Executor

After every command you send to the executor:
1. `sleep 30` — let the executor process
2. `tmux capture-pane -t <executor-session> -p -S -10` — check output
3. If still processing (spinner/working indicator visible): `sleep 60`, check again
4. If idle (prompt visible, no activity): read the output and continue

Do NOT wait for the cron to tell you the executor is done. Check inline after every command.
