---
name: slack-read-messages
description: Sync and inspect Slack message history for this project. Use when the CPO needs the latest inbound message, unread messages, or recent Slack history.
---

# Read Slack Messages

## Sync latest messages from Slack

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json sync
```

## Show unread inbound messages

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json unread --limit 5
```

## Show latest message

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json latest
```

## Show message history

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json history --limit 20
```

## Mark all messages as read

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json mark-read --all
```

## Mark specific count as read

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json mark-read --count 3
```

## Notes

- Always `sync` before reading to get the latest messages.
- Only top-level channel messages are synced. Threaded replies are not automatically ingested.
- Messages from the bot itself are filtered out during sync.
