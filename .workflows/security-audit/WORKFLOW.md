# Security Audit Workflow

## Overview

The security audit is the first **horizontal agent** — a workflow-triggered, bounded supervisor+executor pair that runs a playbook, produces a report, and self-terminates.

This establishes the pattern for all future horizontal agents (performance audits, dependency updates, compliance checks, etc.).

## Session Lifecycle: Bounded TTL Pattern

Horizontal agents differ from project agents: they are **ephemeral**, not persistent. The lifecycle is:

```
Trigger (cron/manual)
  → run.sh dispatches sup+exec pair via launch.py
  → Supervisor reads playbook, directs executor
  → Executor runs checks, writes report
  → Supervisor commits report, states "WORK COMPLETE"
  → Supervisor kills executor session and exits    ← happy path
  → TTL watchdog kills both sessions if stalled    ← safety net
```

### Self-Termination (Happy Path)

The playbook instructs the supervisor:
> "Kill your executor session and exit. Do not wait for further instructions."

This is the expected termination path for all successful runs.

### TTL Safety Net

`run.sh` spawns a background process that kills both sessions after `ttl_minutes` (default: 60). This handles:
- Supervisor gets confused mid-playbook
- Executor hangs on a long-running scan
- Network issues stall the Claude API

The TTL kill is non-negotiable — it prevents runaway agent sessions.

### Session Manifest Integration

For deployments using the session watchdog, register the pair as ephemeral:
```json
{
  "ephemeral": {
    "patterns": ["sup-audit-*", "exec-audit-*"],
    "orphan_ttl_minutes": 60
  }
}
```

The watchdog will clean up orphaned audit sessions that exceed the TTL.

## Reusing This Pattern

To create a new horizontal agent:

1. **Copy the structure:**
   ```
   .workflows/your-audit/
   ├── playbook.md          # What the supervisor reads
   ├── workflow.json         # Schedule + agent config
   ├── run.sh               # Dispatch script with TTL
   ├── report-template.md   # Output format
   └── WORKFLOW.md           # Documentation
   ```

2. **Key fields in workflow.json:**
   - `trigger: "agent"` — tells the scheduler this launches a pair, not a script
   - `agent_config.ttl_minutes` — the TTL for the safety net
   - `agent_config.brief` — path to the playbook
   - `agent_config.branch_prefix` — branch naming convention

3. **Key elements in the playbook:**
   - Numbered steps the supervisor follows
   - Clear scan patterns with safe/unsafe distinctions
   - Severity classifications for findings
   - Explicit self-termination instruction at the end

4. **Key elements in run.sh:**
   - Launch via `launch.py --role pair`
   - Background TTL kill process
   - Branch naming with date suffix

5. **Register in `.workflows/registry.json`**

## Files

| File | Purpose |
|------|---------|
| `playbook.md` | Supervisor instructions — 5 security checks |
| `workflow.json` | Schedule, agent config, output config |
| `run.sh` | Dispatch script with TTL safety net |
| `report-template.md` | Report format for findings |
| `WORKFLOW.md` | This documentation |

## Manual Execution

```bash
bash .workflows/security-audit/run.sh
```

This creates branch `audit/security-YYYY-MM-DD` and launches the pair.
