---
name: slack-enable-communications
description: Enable or disable Slack communications for the current Claude session. Use when setting up a CPO or agent session for Slack message handling.
disable-model-invocation: true
---

# Enable Slack Communications

## Enable session (default CPO setup)

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  enable-session \
  --role CPO \
  --tmux-session cpo \
  --use-latest-seen \
  --start-poller
```

`--use-latest-seen` skips replaying old messages. `--start-poller` launches background polling.

## Check session status

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json session-status
```

## Check poller status

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json poller status
```

## Disable session

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json disable-session
```

## Stop poller

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json poller stop
```

## Notes

- The bot must be invited to the target channel before it can read or post messages.
- Secrets are stored at `~/.config/agent-slack/accounts.json` (never committed).
- Required Slack bot scopes: `chat:write`, `channels:history`, `groups:history`, `im:history`, `im:write`, `files:write`.
