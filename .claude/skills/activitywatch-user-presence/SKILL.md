---
name: activitywatch-user-presence
description: Check whether the user appears active at the computer using the local ActivityWatch AFK watcher before deciding how to contact them.
---

# Check user presence with ActivityWatch

Use this when the CPO wants a quick signal about whether the user appears active before choosing whether to send a Telegram message or wait.

## Default command
```bash
python3 tools/activitywatch_presence.py \
  --json \
  status
```

## Alternate lookback window
```bash
python3 tools/activitywatch_presence.py \
  --json \
  status \
  --minutes 30
```

## Presence history summary
```bash
python3 tools/activitywatch_presence.py \
  --json \
  history \
  --minutes 15
```

## Notes
- The signal is advisory, not authoritative. It reflects ActivityWatch AFK status, not guaranteed attention.
- `not-afk` usually means recent keyboard or mouse activity.
- Audible browser activity can also keep the user marked `not-afk`.
