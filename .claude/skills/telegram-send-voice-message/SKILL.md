---
name: telegram-send-voice-message
description: Send a Telegram voice note to the project owner through the configured bot using the local Kokoro TTS service. Use when a spoken update or question is more useful than text.
---

# Send a Telegram voice note to the user

Use this when the active agent needs to send a concise spoken update or question over Telegram.

## Default CPO command
```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  send-voice \
  --role CPO \
  --message "MESSAGE"
```

## Multiline message
```bash
cat <<'EOF' | python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  send-voice \
  --role CPO \
  --stdin
Line 1
Line 2
EOF
```

## Notes
- Voice notes are synthesized through the local Kokoro TTS service.
- Keep spoken updates concise and natural.
- Longer messages are allowed, but they take longer to synthesize and upload.
- If a long spoken update would be clearer as separate parts, split it manually and use clear continuations like `Part 1 of 2`, `Part 2 of 2`.
- The default voice is project-configured; use CLI overrides only when necessary.
- Tokens are read from `~/.config/agent-telegram/accounts.json`, not from the repo.
