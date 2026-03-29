Send a video to the Telegram chat.

```bash
python3 tools/agent_telegram.py \
  --project-config .agent-comms/telegram.json \
  send-video \
  --role CPO \
  --video /path/to/video.mp4 \
  --caption "Optional caption"
```
