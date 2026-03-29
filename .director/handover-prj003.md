# Director Handover — PRJ-003: Strategic Advisor Role

**Project:** PRJ-003 — Strategic Advisor Role
**Envelope:** `.cpo/projects/prj003-strategic-advisor/envelope.md`
**Briefs:** 2, sequential

---

## Your Mission

Deliver PRJ-003: the Strategic Advisor role for the orchestration framework. Two briefs, executed sequentially.

## Phase A: Role Definition (Brief 1)
- **Brief:** `.cpo/briefs/bl022-strategic-advisor-role.md`
- **Branch:** `feature/bl022-strategic-advisor-role`
- **Size:** L (~2-3 hours)
- **Dispatch:** supervisor+executor pair via `python3 tools/launch.py --role pair --brief .cpo/briefs/bl022-strategic-advisor-role.md --branch feature/bl022-strategic-advisor-role`

After BL-022 completes:
1. Verify commit exists on the branch
2. Report to CPO: "BL-022 complete, ready for merge"
3. **Wait for CPO to merge before dispatching Phase B** — BL-023 depends on BL-022's code being on main

## Phase B: Launch + First Exploration (Brief 2)
- **Brief:** `.cpo/briefs/bl023-strategic-advisor-launch.md`
- **Branch:** `feature/bl023-strategic-advisor-launch`
- **Size:** L (~3-4 hours)
- **Depends on:** BL-022 merged to main
- **Dispatch:** supervisor+executor pair via `python3 tools/launch.py --role pair --brief .cpo/briefs/bl023-strategic-advisor-launch.md --branch feature/bl023-strategic-advisor-launch`

After BL-023 completes:
1. Verify commit exists on the branch
2. Verify evidence files in evidence/bl023-advisor-launch/
3. Report to CPO: "BL-023 complete, PRJ-003 done, ready for merge"

## Important Notes

- Read the project envelope for full context on what the advisor does and why
- The supervisor should read the brief carefully — the advisor methodology is the core deliverable
- BL-023 involves a live test with a running advisor session — the supervisor will need to monitor for ~1-2 hours
- If BL-022's executor stalls, kill and re-dispatch — the deliverables are files, not code, so a fresh start loses nothing
