# Slack Agent Gateway

Project-scoped Slack integration for agent communication. Stdlib-only Python, no pip dependencies.

## Repo Files

| File | Purpose |
|------|---------|
| `tools/agent_slack.py` | CLI tool — all Slack operations |
| `tools/run_slack_poller.sh` | Background poller launcher |
| `.agent-comms/slack.json` | Project config (no secrets, checked in) |
| `.claude/hooks/slack-hook.sh` | Session hook for auto-sync on start/stop |
| `.claude/skills/slack-*/SKILL.md` | Agent skills for Claude Code |

## Local Secret Config

Create `~/.config/agent-slack/accounts.json` (chmod 0600):

```json
{
  "accounts": {
    "my-workspace": {
      "bot_token": "xoxb-XXXXXXXXXXXX-XXXXXXXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXX",
      "bot_user_id": "UXXXXXXXXXX",
      "default_channel": "C07XXXXXXXX"
    }
  }
}
```

### Required Slack Bot Scopes

When creating the Slack app at [api.slack.com/apps](https://api.slack.com/apps), add these Bot Token Scopes:

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages |
| `channels:history` | Read public channel messages |
| `groups:history` | Read private channel messages |
| `im:history` | Read DM messages |
| `im:write` | Open DM conversations |
| `files:write` | Upload files |
| `users:read` | (Optional) Resolve display names |

### Setup Steps

1. Create a new Slack app at [api.slack.com/apps](https://api.slack.com/apps)
2. Under "OAuth & Permissions", add the scopes listed above
3. Install the app to your workspace
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`) to accounts.json
5. Find the bot's user ID (visible in the app settings or via `auth.test`)
6. Invite the bot to the target channel: `/invite @BotName`

## Project Config

`.agent-comms/slack.json` — checked into the repo, no secrets:

```json
{
  "project_id": "my-project",
  "account": "my-workspace",
  "default_channel": "C07XXXXXXXX",
  "channel": "main",
  "enabled_roles": ["CPO"],
  "hook_debounce_seconds": 30,
  "rate_limit": {
    "min_interval_ms": 1100,
    "retry_after_cap_seconds": 30
  },
  "roles": {
    "CPO": {
      "agent_name": "CPO",
      "inbound_mode": "inject",
      "tmux_session": "cpo"
    }
  }
}
```

## Main Commands

### Send a message

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json \
  send --role CPO --message "Status update here"
```

### Reply in a thread

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json \
  send --role CPO --thread-ts "1234567890.123456" --message "Thread reply"
```

### Send a direct message

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json \
  send --role CPO --dm UXXXXXXXXXX --message "Private message"
```

### Upload a file

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json \
  send-file --role CPO --file /path/to/screenshot.png --caption "Build output"
```

### Sync and read messages

```bash
# Fetch latest from Slack
python3 tools/agent_slack.py --project-config .agent-comms/slack.json sync

# Show unread
python3 tools/agent_slack.py --project-config .agent-comms/slack.json unread --limit 5

# Mark as read
python3 tools/agent_slack.py --project-config .agent-comms/slack.json mark-read --all
```

### Verify connection

```bash
python3 tools/agent_slack.py --project-config .agent-comms/slack.json account test
python3 tools/agent_slack.py --project-config .agent-comms/slack.json config validate
```

## Delivery Model

Messages flow to agents via two mechanisms:

1. **Hooks** — fire on Claude session start/stop, triggering a sync + delivery
2. **Poller** — background process that polls every 15 seconds for continuous delivery

Both are optional and independent. The poller ensures messages arrive even while Claude is idle.

## Threading

Slack threads keep channels clean. The CPO can:
- Create a daily status thread anchor, then post updates as replies
- Reply in threads started by other users
- Use `--thread-ts` on any send command

## Session Registration

```bash
# Enable this session for Slack handling (typically run once at CPO startup)
python3 tools/agent_slack.py --project-config .agent-comms/slack.json \
  enable-session --role CPO --tmux-session cpo --use-latest-seen --start-poller
```

## Local State

```
~/.local/share/agent-slack/projects/<project_id>/
  <channel>/
    history.jsonl    # All messages (inbound + outbound)
    state.json       # Sync cursor, timestamps, delivery tracking
  sessions/
    <session_id>.json
  poller.json        # Background poller PID and config
  poller.log         # Poller output
```

## Known Limitations

- Only top-level channel messages are synced. Threaded replies are not automatically ingested (use `conversations.replies` manually if needed).
- The bot must be invited to channels before it can read or post.
- Slack rate limits (~1 req/sec for most methods) are handled with automatic retry, but burst operations may be slow.
- No voice note support (Slack has no native voice notes).

## Troubleshooting

**"not_in_channel" error:** Invite the bot to the channel with `/invite @BotName`.

**Messages not delivering:** Check the poller is running: `python3 tools/agent_slack.py --project-config .agent-comms/slack.json poller status`

**Rate limited:** The tool retries automatically on 429 responses. If persistent, increase `rate_limit.min_interval_ms` in slack.json.

**Config validation fails:** Run `python3 tools/agent_slack.py --project-config .agent-comms/slack.json config validate` and check for placeholder values.
