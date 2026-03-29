---
name: slack-send-file
description: Upload and share a file (image, document, archive) to the configured Slack channel. Use when the CPO needs to share screenshots, build artifacts, or documents via Slack.
---

# Send File to Slack

## Upload a file to the default channel

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send-file --role CPO --file /path/to/file.png --caption "Description"
```

## Upload to a specific channel

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send-file --role CPO --file /path/to/report.pdf \
  --target-channel C07XXXXXXXX --caption "Weekly report"
```

## Upload as a thread reply

```bash
python3 tools/agent_slack.py \
  --project-config .agent-comms/slack.json \
  send-file --role CPO --file /path/to/screenshot.png \
  --thread-ts "1234567890.123456" --caption "Build output"
```

## Notes

- Supports any file type (images, PDFs, archives, text files).
- Uses Slack's modern upload API (files.getUploadURLExternal + files.completeUploadExternal).
- The bot needs `files:write` scope.
- The `--caption` is optional but recommended for context.
