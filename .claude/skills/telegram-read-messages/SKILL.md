---
name: telegram-read-messages
description: Sync and inspect Telegram message history for this project. Use when the CPO needs the latest inbound message, unread messages, or recent Telegram history.
---

# Read Telegram message history for this project

Use this when the active agent needs to inspect recent Telegram communication or unread inbound messages.

## Sync inbound messages first
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  sync
```

## Show unread inbound messages
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  unread \
  --limit 10
```

## Show the latest inbound message
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  latest \
  --direction inbound
```

## Mark all unread inbound messages as read
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  mark-read \
  --all
```

## Notes
- History is stored locally per `project_id + channel`.
- Hook-triggered delivery does not automatically mark messages as read.
- Voice notes are transcribed through the local Speak2 service during `sync` when available.
- If a voice note shows as pending, run `sync` again after Speak2 is ready and loaded.
