# Telegram Agent Gateway

This project includes a local Telegram gateway at `tools/agent_telegram.py`.

## Purpose

- Keep Telegram transport and local message state separate from agent logic
- Support project-scoped history and unread tracking
- Allow only explicitly enabled Claude sessions to receive inbound message delivery
- Reuse the same CLI from Claude Code and Codex

## Repo files

- `.agent-comms/telegram.json`: project-scoped Telegram config, no secrets
- `.claude/settings.json`: Claude hook registration for `SessionStart` and `Stop`
- `.claude/hooks/telegram-hook.sh`: small hook adapter
- `.claude/skills/*/SKILL.md`: Claude skills in the documented format
- `tools/agent_telegram.py`: main transport and local-state CLI

## Local secret config

Create `~/.config/agent-telegram/accounts.json` with permission `0600`:

```json
{
  "accounts": {
    "YOUR_ACCOUNT_NAME": {
      "bot_token": "REPLACE_WITH_BOT_TOKEN"
    }
  }
}
```

You can add more accounts and point other projects at different entries.

## Main commands

Validate config:

```bash
python3 tools/agent_telegram.py config validate
```

Test the configured Telegram account:

```bash
python3 tools/agent_telegram.py account test
```

Enable the current Claude session for CPO communication:

```bash
python3 tools/agent_telegram.py enable-session --role CPO --tmux-session cpo --use-latest-seen --start-poller
```

Send a message:

```bash
python3 tools/agent_telegram.py send --role CPO --message "Need merge approval"
```

Send a voice note:

```bash
python3 tools/agent_telegram.py send-voice --role CPO --message "Quick spoken update"
```

Check Kokoro TTS health:

```bash
python3 tools/agent_telegram.py tts-health
```

Sync inbound messages:

```bash
python3 tools/agent_telegram.py sync
```

Read unread messages:

```bash
python3 tools/agent_telegram.py unread --limit 10
```

Inspect recent voice-transcription status:

```bash
python3 tools/agent_telegram.py voice-status --limit 10
```

Run a background poller every 15 seconds:

```bash
sh ./tools/run_telegram_poller.sh
```

## Claude skill discovery

Claude Code's documented skill format is a directory under `.claude/skills/` containing `SKILL.md`. The Telegram skills are:

- `/telegram-enable-communications`
- `/telegram-send-message`
- `/telegram-send-voice-message`
- `/telegram-read-messages`
- `/activitywatch-user-presence`

## Delivery model

- `SessionStart` and `Stop` hooks both call `hook-check`
- `hook-check` records the Claude `session_id`, then exits unless that session is explicitly enabled
- enabled sessions are role-gated against `.agent-comms/telegram.json`
- `notify` mode posts a short tmux notice
- `inject` mode pastes the latest unread message into the configured tmux session
- `poll` is the continuous alternative if you want tmux delivery even while Claude is idle

## Continuous polling

Preferred setup:

```bash
python3 tools/agent_telegram.py enable-session --role CPO --tmux-session cpo --use-latest-seen --start-poller
```

This enables the session and starts a pinned background poller tied to that exact `session_id`.

Check the current poller:

```bash
python3 tools/agent_telegram.py poller status
```

Stop it:

```bash
python3 tools/agent_telegram.py poller stop
```

## Voice notes

- Telegram `voice` messages are downloaded during `sync`
- Voice notes are converted locally with `ffmpeg`
- The gateway calls the running Speak2 app on `127.0.0.1:8768`
- Successful transcripts are stored as the main inbound message text
- If Speak2 is not ready, the voice note is stored as pending and retried on a later `sync`

## Outbound voice notes

- Outbound voice notes are synthesized through the local Kokoro TTS service on `127.0.0.1:8770`
- Start it with `sh ./tools/run_kokoro_tts_service.sh`
- The gateway converts Kokoro WAV output to Telegram `ogg/opus` and uploads it with `sendVoice`

## Session registration

The hook path writes session records to:

```text
~/.local/share/agent-telegram/projects/<project_id>/sessions/
```

## Local state

Per `project_id + channel`, the gateway stores:

- `history.jsonl`
- `state.json`

under:

```text
~/.local/share/agent-telegram/projects/<project_id>/<channel>/
```
