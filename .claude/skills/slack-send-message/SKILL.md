---
name: slack-send-message
description: Send a Slack message to the configured workspace channel or a specific user DM. Use when the CPO needs to send updates, questions, or escalations via Slack.
---

# Send Slack Message

## Send to default channel

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --message "Your message here"
```

## Send to a specific channel

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --target-channel C07XXXXXXXX --message "Your message here"
```

## Reply in a thread

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --thread-ts "1234567890.123456" --message "Thread reply"
```

## Send a direct message

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --dm UXXXXXXXXXX --message "Private message"
```

## Multiline message via stdin

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --message - <<'EOF'
Line one of the message.
Line two of the message.
EOF
```

## Send without agent name prefix

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send --role CPO --raw --message "No [CPO] prefix"
```

## Notes

- Messages are prefixed with `[AgentName]` by default. Use `--raw` to skip the prefix.
- The bot must be in the target channel. Use `--dm` for direct messages to users.
- Thread replies keep the channel clean — use `--thread-ts` for follow-up messages.
