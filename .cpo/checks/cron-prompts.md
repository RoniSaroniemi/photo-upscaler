# CPO Cron Prompts

## 30-Minute Quick Check

```
Quick check cycle. Read .cpo/daily-todo.md for today's priorities. Check active work:
1. List tmux sessions: tmux -L photo-upscaler ls 2>/dev/null || tmux ls 2>/dev/null
2. For any active supervisor/executor sessions, check their last output (tmux capture-pane)
3. Read .director/registry.json — any completed or stalled projects?
4. If work completed: verify it, merge if passing, update roadmap
5. If work stalled (>30min no progress): diagnose and intervene
6. Check Telegram for CEO messages: /telegram-read-messages
7. If idle (no active work): pick next priority from daily-todo and dispatch it
Report status briefly, then return to idle.
```

## Shift Start (use at beginning of each session)

```
Shift start. Full context rebuild:
1. Read .cpo/lifecycle.md — current stage and what's allowed
2. Read .cpo/daily-todo.md — today's priorities
3. Read .cpo/roadmap.md — sprint items
4. Check .director/registry.json — active projects
5. Check Telegram: /telegram-read-messages
6. Set up 30-minute cron loop
7. Determine first action and execute
```
