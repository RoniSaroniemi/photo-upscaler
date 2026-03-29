---
name: telegram-send-message
description: Send a Telegram message to the project owner through the configured bot. Use when the CPO needs to send a concise update, question, approval request, or escalation.
---

# Send a Telegram message to the user

Use this when the active agent needs to send a concise update or question over Telegram.

## Default CPO command
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  send \
  --role CPO \
  --message "MESSAGE"
```

## Multiline message
```bash
cat <<'EOF' | python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  send \
  --role CPO \
  --stdin
Line 1
Line 2
EOF
```

## Notes
- Messages are prefixed with the configured agent label, for example `[CPO]`.
- Tokens are read from `~/.config/agent-telegram/accounts.json`, not from the repo.
