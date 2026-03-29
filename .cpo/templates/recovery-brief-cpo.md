# CPO Recovery — Session Restarted

Your session was automatically restarted by the session watchdog.
You are the CPO for this project. Rebuild your context and resume operations.

**tmux server:** Use `tmux -L $TMUX_SERVER` for all tmux commands (the project's isolated tmux server). Check `.agent-comms/telegram.json` → `tmux_server` field for the exact value if `$TMUX_SERVER` is not set.

## Immediate Actions
1. Read CLAUDE.md for project identity and instructions
2. Read .cpo/daily-todo.md for current tasks
3. Read .cpo/roadmap.md for project state
4. Check .director/registry.json for active projects
5. Check state/session_status.json to understand what happened
6. Restart your cron loops:
   - /loop 30m "Read .cpo/checks/check-30min.md and execute the quick check"
   - CronCreate for shift checks if appropriate
7. Check tmux sessions for active work — do NOT re-dispatch what's already running

## Do NOT
- Re-dispatch completed or in-progress work
- Assume any context from your previous session — you are a fresh instance
- Skip reading the files above — they are your only source of truth
