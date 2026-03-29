---
name: telegram-enable-communications
description: Enable or disable Telegram communications for the current Claude session. Use when setting up the CPO session or checking whether this session is the Telegram-handling session.
disable-model-invocation: true
---

# Enable Telegram communications for this Claude session

Use this when the current Claude Code session should receive Telegram-driven inbound communication.

## Default CPO command
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  enable-session \
  --role CPO \
  --tmux-session cpo \
  --use-latest-seen \
  --start-poller
```

## Check current registration
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  session-status \
  --use-latest-seen
```

## Check background poller
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  poller \
  status
```

## Disable this session
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  disable-session \
  --use-latest-seen \
  --stop-poller
```

## Notes
- `--use-latest-seen` uses the most recently hook-observed Claude session in this project.
- If multiple Claude sessions are active and this resolves to the wrong one, run `session-status --all --json` and then repeat with `--session-id ...`.
- Only enabled roles listed in `.agent-comms/telegram.json` will react to `SessionStart` and `Stop` hooks.
- `--start-poller` starts a pinned 15-second background poller for the selected session, so Telegram injection keeps working even while Claude is idle.
