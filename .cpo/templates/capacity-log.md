# Capacity Log

This log tracks shift-by-shift work output across all agents working on the project. Each entry records what was accomplished, how long the shift lasted, and any blockers encountered. Use this to measure throughput, identify patterns, and plan future capacity.

<!--
  CAPACITY LOG TEMPLATE
  =====================
  How to use:
  1. Add a new entry at the TOP of this file for each shift worked (newest first).
  2. Copy the entry format below and fill in all fields.
  3. Shift Types: Morning, Afternoon, Night.
  4. Duration should use 24-hour format (e.g., 09:00-13:00).
  5. Tasks Completed: list each discrete deliverable as a bullet point.
  6. Blockers: list anything that slowed or stopped progress, or write "None".
  7. Notes: optional free-text for context that doesn't fit elsewhere.
-->

<!-- ENTRY FORMAT (copy this for each new shift):

## YYYY-MM-DD — [Shift Type]

**Agent:** [agent name or session identifier]
**Duration:** [HH:MM]-[HH:MM]

**Tasks Completed:**
- [Task 1: brief description of what was delivered]
- [Task 2: brief description of what was delivered]

**Blockers:**
- [Blocker description, or "None"]

**Notes:**
[Any additional context, observations, or handover details.]

---

-->

<!-- EXAMPLE ENTRY (remove this comment block when adding real entries):

## 2026-01-15 — Morning

**Agent:** cpo-executor-1
**Duration:** 09:00-13:00

**Tasks Completed:**
- Created initial project scaffolding and directory structure
- Implemented user authentication endpoint with JWT tokens
- Wrote unit tests for auth module (12 tests, all passing)

**Blockers:**
- Waited 30 minutes for CI pipeline to become available

**Notes:**
Auth module is complete but needs integration testing with the frontend.
Left a TODO in `src/auth/middleware.ts` for rate limiting — not in scope for this shift.

---

-->
