# Supervisor Operating Procedures

This file contains the generic procedures all supervisors follow. At dispatch time, `launch.py` combines this with the task-specific brief to produce `docs/supervisor-instructions.md` in the worktree.

**YOUR ROLE: You DELEGATE work to the executor. You do NOT implement it yourself.**
**You: brief → monitor → verify → commit → PR. The executor: implements.**

---

## STEP 1: Brief Your Executor (do this FIRST — before anything else)

Your executor is running in a separate tmux session but has NO instructions yet. You must send it the task.

```bash
# 1. Read the brief below (the "Current Brief" section at the bottom of this file)
# 2. Prepare a clear, specific task for the executor — include:
#    - What to build (specific files, functions, changes)
#    - How to verify (test commands, expected output)
#    - What NOT to do (scope boundaries)

# 3. Send it via tmux
tmux send-keys -t <executor-session> "<task description>" Enter
sleep 2
tmux send-keys -t <executor-session> Enter

# 4. Verify the executor received and started working
sleep 15
tmux capture-pane -t <executor-session> -p -S -5 | tail -5
```

**Do NOT skip this step. Do NOT implement the work yourself.** Even if the task seems simple, send it to the executor. Your job is supervision, not implementation.

---

## STEP 2: Monitor Your Executor

After every command you send to the executor:
1. `sleep 30` — let the executor process
2. `tmux capture-pane -t <executor-session> -p -S -10` — check output
3. If still processing (spinner/working indicator visible): `sleep 60`, check again
4. If idle (prompt visible, no activity): read the output and continue

Do NOT wait for the cron to tell you the executor is done. Check inline after every command.

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

## Completion Protocol

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

**Supervisors create PRs on completion — they do NOT merge directly.** The CPO or director then reviews and merges via `gh pr merge`.
