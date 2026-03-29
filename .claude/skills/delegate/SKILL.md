---
name: delegate
description: Launch agents — supervisor+executor pairs, directors, or CPOs. Creates sessions, launches providers, injects briefs, sets up cron, and verifies.
---

# Launch Agents

Unified launcher for all agent roles. Replaces manual session setup.

## Usage

### Pair (supervisor + executor)
```bash
python3 tools/launch.py --role pair --brief <path> --branch <branch> [--provider claude|codex] [--tmux-server <server>]
```

### Director (director + subconscious)
```bash
python3 tools/launch.py --role director [--handover <path>] [--provider claude|codex] [--tmux-server <server>]
```

### CPO (CPO + subconscious)
```bash
python3 tools/launch.py --role cpo [--provider claude|codex] [--tmux-server <server>] [--skip-comms]
```

## Examples

### Delegate a pair with Claude (default)
```bash
python3 tools/launch.py --role pair --brief .cpo/briefs/my-task.md --branch feature/my-task
```

### Delegate a pair with Codex executor
```bash
python3 tools/launch.py --role pair --brief .cpo/briefs/my-task.md --branch feature/my-task --provider codex
```

### Launch a director with handover
```bash
python3 tools/launch.py --role director --handover .director/handover-to-director.md
```

### Launch CPO without comms
```bash
python3 tools/launch.py --role cpo --skip-comms
```

### Dry run (see what would happen)
```bash
python3 tools/launch.py --role pair --brief .cpo/briefs/my-task.md --branch feature/my-task --dry-run
python3 tools/launch.py --role director --dry-run
python3 tools/launch.py --role cpo --dry-run
```

### JSON output
```bash
python3 tools/launch.py --role pair --brief .cpo/briefs/my-task.md --branch feature/my-task --json
```

## What It Does

### --role pair
1. Creates a git worktree for isolated work
2. Copies the brief into the worktree
3. Creates supervisor + executor tmux sessions
4. Launches Claude or Codex in both sessions
5. Injects the brief into the supervisor
6. Verifies both agents are running

### --role director
1. Creates director + director-subconscious tmux sessions
2. Launches provider in both sessions
3. Injects handover (if provided) and subconscious brief
4. Sets up recurring checks (Claude: /loop, Codex: crontab)
5. Verifies both sessions active

### --role cpo
1. Creates CPO + CPO-subconscious tmux sessions
2. Launches provider in both sessions
3. Injects CPO brief and subconscious brief
4. Sets up recurring checks (Claude: /loop, Codex: crontab)
5. Enables Telegram poller (unless --skip-comms)
6. Verifies both sessions active

## Backward Compatibility

`tools/delegate.py` still works — it forwards to `tools/launch.py --role pair`.

## When To Use
- You have a brief to dispatch to a supervisor+executor team
- You need to launch a director for multi-project orchestration
- You need to launch a CPO for full project management
- Use this instead of manually creating tmux sessions and briefing agents
