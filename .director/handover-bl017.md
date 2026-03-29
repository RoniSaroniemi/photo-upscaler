# Director Handover — BL-017 Operations Loop v2

**Date:** 2026-03-27
**Dispatched by:** CPO (Forge)
**Project root:** /Users/roni-saroniemi/Github/claude-orchestration

---

## Your Mission

Implement Operations Loop v2 in 6 briefs. Use `python3 tools/launch.py --role pair` to dispatch.

## Briefs (in execution order)

| # | Brief | File | Effort | Branch | Depends On |
|---|-------|------|--------|--------|------------|
| 1 | Queue Daemon | `.cpo/briefs/bl017-1-queue-daemon.md` | L (~2h) | `feature/bl017-queue-daemon` | None |
| 2 | Discovery Loop | `.cpo/briefs/bl017-2-discovery-loop.md` | XL (~4h) | `feature/bl017-discovery-loop` | 1 |
| 3 | Method Analyst | `.cpo/briefs/bl017-3-method-analyst.md` | M (~1h) | `feature/bl017-method-analyst` | 1 |
| 4 | Source Memory | `.cpo/briefs/bl017-4-source-memory.md` | M (~1h) | `feature/bl017-source-memory` | 3 |
| 5 | launch.py --role queue | `.cpo/briefs/bl017-5-launch-queue.md` | M (~1h) | `feature/bl017-launch-queue` | 1 |
| 6 | E2E System Test | `.cpo/briefs/bl017-6-e2e-system-test.md` | XXL (~8h) | `feature/bl017-e2e-test` | 1-5 |

## Concurrency Rules

- Max 2 concurrent pairs normally
- Briefs 1+5 can run in parallel (both independent, 5 is small)
- Briefs 2+3 can run in parallel after 1 completes (independent of each other)
- Brief 4 depends on 3
- Brief 6 depends on all previous

## Dispatch Pattern

```
Phase A: Brief 1 (queue daemon) + Brief 5 (launch --role queue) — parallel
Phase B: Brief 2 (discovery) + Brief 3 (method analyst) — parallel, after Phase A merged
Phase C: Brief 4 (source memory) — after Brief 3 merged
Phase D: Brief 6 (E2E system test) — after all merged
```

## Merge Protocol

After each brief completes:
1. Report to CPO: "Brief N complete — branch ready for merge"
2. Wait for CPO merge confirmation
3. Create next worktree from updated main

## Operational Notes

- All agents use `claude --dangerously-skip-permissions`
- crawl4ai is at /Users/roni-saroniemi/Github/crawl4ai — Brief 2 needs it
- If a pair stalls 2+ checks: kill and re-dispatch
- Brief 6 is the longest — it runs the full system. Budget 4+ hours.
