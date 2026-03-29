# Operations Loop — User Guide

The Operations Loop is the third execution primitive in the orchestration framework. It handles **queue-driven, semi-open repeated work** — processing many items with concurrent workers, learning from each batch, and improving over time.

**When to use it:**
- Processing a list of URLs, accounts, or data points
- Repeated tasks where each item is similar but not identical
- Work that benefits from learning (extraction improves, bottlenecks get removed)
- Tasks suited for cheap executor agents (Codex) with rare supervision

**When NOT to use it:**
- One-off project work → use the Hierarchy (CPO → Director → Supervisor → Executor)
- Deterministic scheduled pipelines → use Workflows

---

## How It Works

```
CPO decides to start a queue
    │
    ▼
CPO creates queue config + executor prompt
    │
    ▼
CPO launches Queue Director (via launch.py --role director)
    │
    ▼
Queue Director manages everything:
    ├── Checks queue state (every 4 min cron)
    ├── Dispatches workers for ready items
    ├── Collects results and verifies artifacts
    ├── Triggers learning cycles at configured intervals
    ├── Updates executor prompt based on learnings
    └── Runs until queue is empty or budget exhausted
```

---

## The Agents

| Agent | Role | Provider | Lifecycle |
|-------|------|----------|-----------|
| **Queue Director** | Manages the queue, dispatches workers, triggers learning | Claude Opus | Persistent (for the duration of the queue) |
| **Queue Director Subconscious** | Monitors the Queue Director for stalls | Claude Sonnet | Persistent |
| **Worker** | Processes one item (fetch, extract, assess) | Codex (cheap) | Ephemeral — spawned per item or small batch, dies after completion |

---

## Step-by-Step: Starting a Queue

### 1. Create the Queue Directory

```bash
mkdir -p .operations/my-queue/{artifacts,methods}
```

### 2. Write the Queue Config (`queue.json`)

Copy from the template and customize:

```bash
cp .operations/queue-template/queue.json .operations/my-queue/queue.json
```

Key settings to configure:

```json
{
  "queue_id": "my-queue",
  "name": "Human-readable name",
  "description": "What this queue does",

  "concurrency": {
    "max_workers": 2,
    "worker_provider": "codex",
    "worker_timeout_minutes": 10
  },

  "budget": {
    "max_queue_size": 1000,
    "max_items_per_day": 100,
    "backlog_threshold": 50
  },

  "learning": {
    "ramp_up": [
      {"items": 2, "mode": "intense"},
      {"items": 4, "mode": "medium"},
      {"items": null, "mode": "short"}
    ],
    "review_interval_continuous": 20
  },

  "item_schema": {
    "url": "string, required",
    "...": "your custom fields"
  },

  "artifact_schema": {
    "...": "what each completed item produces"
  }
}
```

### 3. Write the Executor Prompt

Create `.operations/my-queue/executor-prompt.md` — the instructions each worker receives:

```markdown
# Worker Instructions

## Your Task
[What to do with each item — fetch, extract, analyze, etc.]

## Item Data
[INJECTED AT DISPATCH TIME — the item's fields from the queue]

## Output
Write your result as JSON to the artifact path provided.
The artifact must match the schema defined in queue.json.
```

### 4. Write the Queue Director Handover

Create `.operations/my-queue/queue-director-handover.md`:

```markdown
# Queue Director Handover

**Queue ID:** my-queue
**Config:** .operations/my-queue/queue.json
**Database:** .operations/my-queue/queue.db
**Executor prompt:** .operations/my-queue/executor-prompt.md

## Your Job
1. Initialize the queue
2. Add items
3. Run the processing loop with learning ramp-up
4. Collect artifacts
5. Report when complete
```

### 5. Initialize the Queue and Add Items

```bash
# Initialize the SQLite database
python3 tools/queue_runner.py init --config .operations/my-queue/queue.json

# Add items one by one
python3 tools/queue_runner.py add --config .operations/my-queue/queue.json --url "https://..."

# Or add from a file (one URL per line)
python3 tools/queue_runner.py add --config .operations/my-queue/queue.json \
  --batch-file .operations/my-queue/items.txt
```

### 6. Launch the Queue Director

```bash
python3 tools/launch.py --role director \
  --handover .operations/my-queue/queue-director-handover.md
```

This creates:
- A `director` tmux session with the Queue Director
- A `director-subconscious` tmux session monitoring it
- Both agents launched with the configured provider

### 7. The Queue Director Takes Over

From this point, the Queue Director manages everything autonomously:

```
Cron fires every 4 minutes:
    │
    ├── 1. Check queue state
    │   python3 tools/queue_runner.py status --config <config>
    │   → ready=12, claimed=2, completed=8, failed=1
    │
    ├── 2. Check learning phase
    │   → Are we due for a learning cycle?
    │   → If yes: pause, review, update prompt, resume
    │
    ├── 3. Dispatch workers
    │   For each open slot (running < max_workers):
    │   → Claim item: python3 tools/queue_runner.py claim --config <config> --worker-id worker-N
    │   → Write worker brief: executor-prompt.md + item data
    │   → Launch worker (Codex executor)
    │
    ├── 4. Collect results
    │   For each running worker:
    │   → Check if completed (artifact exists)
    │   → Verify artifact matches schema
    │   → python3 tools/queue_runner.py complete --config <config> --item-id ITEM-NNN --artifact-path <path>
    │
    └── 5. Health check
        → Within daily budget?
        → Systemic errors? (same error 3+ times → escalate)
```

---

## The Learning Ramp-Up

The queue doesn't just process items — it gets better over time.

```
Phase 1: INTENSE (first 2 items)
├── Process 2 items slowly
├── Queue Director reviews every artifact in detail
├── Identifies: what worked, what failed, what was slow
├── Updates executor-prompt.md with improvements
└── Writes methods/iteration-1.md

Phase 2: MEDIUM (next 4 items)
├── Process 4 items with updated prompt
├── Director reviews: did the changes help?
├── Further refinements
└── Writes methods/iteration-2.md

Phase 3: SHORT → CONTINUOUS (remaining items)
├── Process remaining items at full throughput
├── Light review every 20 items
├── Minor adjustments only
└── Runs until queue empty or budget exhausted
```

The ramp-up is configurable in `queue.json`. The pattern: **start slow and learn, then accelerate.**

---

## Queue Runner Commands

```bash
# Initialize database
python3 tools/queue_runner.py init --config <queue.json>

# Add items
python3 tools/queue_runner.py add --config <queue.json> --url "https://..."
python3 tools/queue_runner.py add --config <queue.json> --batch-file items.txt

# Check status
python3 tools/queue_runner.py status --config <queue.json>
# Output: ready=12, claimed=2, completed=8, failed=1, total=23

# List items with filter
python3 tools/queue_runner.py list --config <queue.json> --status ready [--json]

# Claim next item (used by workers)
python3 tools/queue_runner.py claim --config <queue.json> --worker-id worker-1

# Complete an item
python3 tools/queue_runner.py complete --config <queue.json> --item-id ITEM-001 \
  --artifact-path artifacts/ITEM-001.json

# Mark item failed
python3 tools/queue_runner.py fail --config <queue.json> --item-id ITEM-001 --error "reason"

# Retry a failed item
python3 tools/queue_runner.py retry --config <queue.json> --item-id ITEM-001
```

---

## Directory Structure

```
.operations/
├── queue-template/          # Template for new queues
│   └── queue.json           # Config template
│
├── my-queue/                # One directory per queue
│   ├── queue.json           # Queue configuration
│   ├── queue.db             # SQLite database (items + state)
│   ├── executor-prompt.md   # Worker instructions (evolves via learning)
│   ├── queue-director-handover.md  # Director's operating instructions
│   ├── items.txt            # Item list (if batch-loaded)
│   ├── artifacts/           # One JSON file per completed item
│   │   ├── ITEM-001.json
│   │   └── ITEM-002.json
│   └── methods/             # Learning iteration records
│       ├── iteration-1.md
│       └── iteration-2.md
```

---

## Monitoring

### From the CPO

```bash
# Check queue health
python3 tools/queue_runner.py status --config .operations/my-queue/queue.json

# View the Queue Director's activity
tmux capture-pane -t director -p -S -20

# Check artifacts
ls .operations/my-queue/artifacts/ | wc -l

# Read learning iterations
cat .operations/my-queue/methods/iteration-1.md
```

### From the `orch` CLI

```bash
python3 tools/orch.py status
# Shows the Queue Director session alongside other agents
```

---

## Example: Tori.fi Scanner

The first queue built with this system scans Finnish second-hand marketplace listings:

- **15 items** processed end-to-end
- **3 learning iterations** refined the extraction prompt
- **Artifacts** contain: title, price, category, condition, and a value assessment (good buy / fair / overpriced with reasoning)
- **Workers:** Codex executors fetching and analyzing each listing

See `.operations/tori-scanner/` for the complete working example.

---

## What's Next (Future Enhancements)

- **Discovery loop:** Agent that finds new items when the backlog runs low
- **Method Analyst:** Dedicated agent for deeper learning analysis (separate from Queue Director)
- **launch.py --role queue:** One-command queue initiation
- **Source memory:** Remember how each item was processed for efficient re-checks
- **Skill graduation:** When a method stabilizes, promote it to the skill library
