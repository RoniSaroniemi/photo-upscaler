# Source Memory — Graduated Refresh Modes

## Overview

Source memory records HOW items were retrieved, enabling increasingly efficient
refresh methods as patterns stabilize. Each item progresses through graduated
refresh modes, from full agent re-processing to deterministic script execution.

## Refresh Modes

### 1. `none` — No Refresh
Item is collected once and never refreshed. Suitable for historical data or
one-time snapshots.

### 2. `agent_recheck` — Full Agent (Default)
The queue daemon dispatches a full agent worker to re-process the item from
scratch. This is the starting mode for all items.

- **When:** Item has no source memory, or source memory is incomplete.
- **Cost:** High — full agent invocation per item.
- **Accuracy:** Highest — agent adapts to page changes.

### 3. `efficient_recheck` — Selector-Based Quick Check
Uses CSS selectors stored in `source_memory.key_selectors` to fetch the URL
via HTTP and extract key fields. Only dispatches a full agent if changes are
detected.

- **When:** Item has source memory with reliable key_selectors.
- **Cost:** Low for unchanged items (HTTP fetch + parse), full agent only on change.
- **Accuracy:** High for change detection, but may miss JS-rendered fields.

```bash
# Quick-check a single item
python3 tools/queue_runner.py quick-check --config .operations/tori-scanner/queue.json --item-id ITEM-001

# Batch refresh check (finds all stale items)
python3 tools/queue_runner.py refresh-check --config .operations/tori-scanner/queue.json
```

### 4. `deterministic_script` — Generated Script
A Python script (proposed by Method Analyst, approved by Director) handles the
full extraction. Agent is only invoked if the script fails.

- **When:** Method Analyst identifies a stable pattern (20+ items, same selectors, <5% error).
- **Cost:** Minimal — runs a Python script with HTTP/crawl4ai.
- **Accuracy:** >= 95% (tested against known artifacts before deployment).

## Graduation Path

```
┌─────────────────┐
│  New Item Added  │
│  (no source mem) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Method Analyst records
│  agent_recheck  │────►  key_selectors from
│  (full agent)   │       artifact analysis
└────────┬────────┘
         │ source_memory populated
         ▼
┌─────────────────────┐     Quick HTTP check,
│  efficient_recheck  │────►  agent only if
│  (selector-based)   │       fields changed
└────────┬────────────┘
         │ 20+ items with same selectors, <5% error
         ▼
┌─────────────────────────┐     Analyst proposes script,
│  deterministic_script   │────►  Director approves,
│  (generated Python)     │       tested vs. 5 known items
└─────────────────────────┘
```

## Source Memory Schema

Each completed item stores a `source_memory` JSON blob in the database:

```json
{
  "retrieval_method": "agent_recheck",
  "last_retrieval_path": "HTTP GET → parse HTML → extract meta tags",
  "key_selectors": {
    "title": "meta[property=og:title]",
    "price": ".listing-price .amount"
  },
  "refresh_script": null,
  "script_accuracy": null,
  "method_stable_since": null
}
```

| Field | Description |
|-------|-------------|
| `retrieval_method` | Current refresh mode for this item |
| `last_retrieval_path` | Human-readable description of how data was fetched |
| `key_selectors` | Map of field names to CSS selectors / meta tag paths |
| `refresh_script` | Path to approved deterministic script (if graduated) |
| `script_accuracy` | Measured accuracy of the script (0.0–1.0) |
| `method_stable_since` | ISO date when the pattern was deemed stable |

## Queue Config

Enable refresh in `queue.json`:

```json
{
  "refresh": {
    "enabled": true,
    "mode": "efficient_recheck",
    "interval_days": 7,
    "stale_after_days": 30
  }
}
```

| Field | Description |
|-------|-------------|
| `enabled` | Whether automatic refresh checking is active |
| `mode` | Default refresh mode: `none`, `agent_recheck`, `efficient_recheck`, `deterministic_script` |
| `interval_days` | Re-check items after this many days since last completion |
| `stale_after_days` | Force full agent recheck after this many days (overrides mode) |

## Script Development Workflow

1. **Method Analyst identifies pattern:** After reviewing 20+ artifacts, the analyst
   sees the same CSS selectors work reliably across items.

2. **Analyst proposes script:** Writes `methods/script-proposal-N.py` using the
   template in `methods/script-proposal-template.py`.

3. **Director reviews:** Reads the proposal, checks the selectors match evidence.

4. **Testing:** Script is run against 5 known items with existing artifacts.
   Output is compared field-by-field. Accuracy must be >= 95%.

5. **Deployment:** If approved:
   - Script is saved to `methods/refresh-script-N.py`
   - Item's `source_memory.refresh_script` is set to the script path
   - Item's `source_memory.retrieval_method` is set to `deterministic_script`
   - Item's `source_memory.script_accuracy` is set to the measured accuracy

6. **Fallback:** If the script fails at runtime, the item falls back to
   `agent_recheck` for that refresh cycle. Persistent failures (3+) trigger
   re-analysis by the Method Analyst.

## CLI Commands

```bash
# Write source memory to an item
python3 tools/queue_runner.py update-source-memory \
  --config .operations/tori-scanner/queue.json \
  --item-id ITEM-001 \
  --json '{"retrieval_method":"efficient_recheck","key_selectors":{"title":"meta[property=og:title]"}}'

# Find items due for refresh and re-queue them
python3 tools/queue_runner.py refresh-check \
  --config .operations/tori-scanner/queue.json

# Quick-check a single item using stored selectors
python3 tools/queue_runner.py quick-check \
  --config .operations/tori-scanner/queue.json \
  --item-id ITEM-001 --json
```
