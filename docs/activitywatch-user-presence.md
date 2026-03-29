# ActivityWatch User Presence

This project now includes a small local ActivityWatch presence reader at `tools/activitywatch_presence.py`.

## Purpose

- give the CPO a quick signal about whether the user appears active at the computer
- support communication decisions before sending Telegram messages
- keep the signal read-only and separate from the Telegram transport

## Local dependency

The tool expects a local ActivityWatch server at `http://127.0.0.1:5600`.

It reads the local `afkstatus` bucket, which on this machine resolves to `aw-watcher-afk_Mac`.

## Main commands

Detect the default AFK bucket:

```bash
python3 tools/activitywatch_presence.py detect
```

Read the current presence snapshot:

```bash
python3 tools/activitywatch_presence.py --json status
```

Read a 15-minute AFK vs active summary:

```bash
python3 tools/activitywatch_presence.py --json history --minutes 15
```

## Output model

`status` returns:

- `is_active_now`
- `current_status`
- `status_since`
- `last_seen_active_at`
- `active_seconds`
- `afk_seconds`
- `lookback_minutes`
- `bucket_id`

## Interpretation note

This is an advisory presence signal, not guaranteed attention.

- `not-afk` usually means recent input activity
- `afk` means ActivityWatch considers the user away based on inactivity threshold
- audible browser playback can keep the user marked `not-afk`

Use this as one communication hint for the CPO, not as a hard rule.
