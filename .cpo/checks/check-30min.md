# 30-Minute Quick Check

Run this cycle every 30 minutes.

## Steps

1. **Active sessions** — `tmux -L photo-upscaler ls 2>/dev/null` — are all expected sessions alive?
2. **Director registry** — Read `.director/registry.json` — any completed or stalled projects?
   - Completed → verify, merge, update roadmap
   - Stalled (>30min no output change) → diagnose, intervene
3. **Daily TODO** — Read `.cpo/daily-todo.md` — what's the next unblocked priority?
4. **Telegram** — `/telegram-read-messages` — any CEO messages or approvals?
5. **Decide** — If idle with no active work: pick the highest-priority item and dispatch it.

## Quick Health Checks

```bash
# Sessions alive?
tmux -L photo-upscaler ls 2>/dev/null

# Any active supervisor/executor pairs?
tmux -L photo-upscaler ls 2>/dev/null | grep -E "^(sup|exec)-"

# Director registry status
python3 -c "import json; r=json.load(open('.director/registry.json')); active=[p for p in r['projects'] if p['status'] not in ('complete','cancelled')]; print(f'{len(active)} active, {len(r[\"projects\"])} total')"
```
