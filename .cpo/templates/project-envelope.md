# Project Envelope: [Project Name]

**Project ID:** PRJ-[NNN]
**Status:** planning | experiments | executing | testing | complete
**Created:** [date]
**Briefs:** [list of BL-NNN IDs]

---

## 1. Objective

*What does this project achieve when ALL briefs are done? This is the "so what" — the user-visible or system-visible outcome that no single brief delivers alone.*

[One paragraph describing the end state. Be specific about what changes for the user, the system, or the team.]

> **Why this section matters:** Individual briefs solve pieces. The envelope ensures the pieces add up to something coherent. Without a clear objective, briefs drift in scope and the integration phase reveals misalignment.

---

## 2. Experiments (Viability Probes)

*Quick, targeted experiments to confirm that the approach is viable BEFORE writing implementation briefs. Each experiment answers a specific yes/no question. If an experiment fails, the project scope or approach changes before any implementation work is wasted.*

| # | Question | Method | Result | Impact on Plan |
|---|----------|--------|--------|---------------|
| 1 | [Can X work?] | [How to test — CLI command, prototype, API call] | pending / yes / no | [What changes if no] |
| 2 | [Is Y available?] | [Method] | pending | [Impact] |

> **Why this section matters:** The fork experiment (BL-018) saved hours — we confirmed `--fork-session` works before writing 500 lines of brief. Without experiments, briefs contain untested assumptions that surface as blockers mid-implementation. Run experiments before briefing, not during.

**When to experiment:**
- New external dependency (API, tool, library) — does it actually work?
- Uncertain integration point — do these two things compose correctly?
- Performance concern — is the approach fast enough?
- Permission/access question — can we reach this resource?

**When NOT to experiment:**
- Standard patterns we've used before (tmux sessions, worktrees, crontab)
- Pure code tasks with no external dependencies
- Simple refactoring or enhancement of existing tools

---

## 3. Brief Split

*The ordered list of briefs with dependencies. Each brief should be independently mergeable and verifiable. Mark which briefs can run in parallel.*

```
Phase A (parallel):
  Brief 1: [BL-NNN] [title] — [S/M/L/XL] — [one-line scope]
  Brief 2: [BL-NNN] [title] — [S/M/L/XL] — [one-line scope]

Phase B (after Phase A merges):
  Brief 3: [BL-NNN] [title] — [M] — [scope]

Phase C (after Phase B merges):
  Brief 4: [BL-NNN] [title] — [L] — E2E integration test
```

> **Why this section matters:** Without an explicit dependency graph, the director dispatches briefs that fail because prerequisites aren't merged yet. The phase structure also tells the CPO when to intervene (merge between phases) vs when to let it run.

**Guidelines for splitting:**
- Each brief should take 1-4 hours of agent execution time
- If a brief is > XL, split it further
- Put experiment briefs at the start (Phase 0)
- Put E2E test briefs at the end (final phase)
- Shared infrastructure briefs go early — multiple later briefs depend on them

---

## 4. Integration Plan

*What needs to work ACROSS briefs that isn't covered by any single brief's tests? These are the seams — where Brief A's output connects to Brief B's input.*

| Integration Point | Briefs Involved | What to Verify | How to Verify |
|-------------------|----------------|----------------|---------------|
| [e.g., "fork helper reused by planning"] | BL-018 + BL-019 | [Function interface matches] | [Call from both contexts] |

> **Why this section matters:** Individual briefs pass their own tests but the system breaks at integration points. BL-017's E2E test (Brief 6) caught real bugs — codex exec hanging, stale seed URLs — that no component test found. Identifying integration points upfront makes the E2E test focused rather than exploratory.

---

## 5. E2E Test Plan

*The definitive test that proves the whole project works. This must be an EXECUTABLE SCRIPT, not just a checklist. The script runs the actual user journey and reports pass/fail.*

**Scenario:** [Concrete, realistic test scenario with specific inputs and expected outputs]

**Test script** (create as `scripts/e2e-test.sh` or `tests/e2e.spec.ts`):
```bash
# This script MUST be executable and produce clear pass/fail output.
# It should test the ACTUAL user journey, not just check HTTP status codes.
# Include: real file uploads, real form submissions, real payment flows (test mode).
# Example:
#   1. Start the app
#   2. Upload a test image (include test-image.jpg in the repo)
#   3. Verify output image dimensions > input
#   4. Check cost was calculated correctly
#   5. Verify balance was deducted
```

**Verification level required:** Level 3 minimum (flow works end-to-end). See lifecycle.md Verification Levels.

**Verification Checklist:**
| # | Check | Expected | How to Verify | Level |
|---|-------|----------|---------------|-------|
| 1 | [Check] | [Expected result] | [Command or observation] | [2/3/4] |

**Model/Cost:** [Which model to use for E2E test — typically sonnet or haiku for cost efficiency]

> **Why this section matters:** Defining the E2E test before implementation ensures briefs produce testable artifacts. Without it, the final test brief has to figure out what to test — which means discovering integration issues at the worst possible time.

---

## 6. Success Criteria

*How do we know the project is DONE — not just that all briefs merged, but that the objective from Section 1 is achieved?*

- [ ] [Criterion 1 — maps to the objective]
- [ ] [Criterion 2]
- [ ] [E2E test passes]
- [ ] [Documentation updated if user-facing]

> **Why this section matters:** "All briefs merged" ≠ "project successful." BL-017 had all 5 implementation briefs merged but only the E2E test (Brief 6) confirmed the system actually worked. Success criteria prevent premature closure.

---

## 7. Dispatch Strategy

*How should this project be executed? This guides the CPO and director.*

| Option | When to Use |
|--------|-------------|
| **Direct dispatch** (CPO → sup+exec pairs) | ≤ 3 briefs, no complex dependencies |
| **Director-managed** (CPO → director → pairs) | 4+ briefs, phased dependencies |
| **Planning pipeline first** (launch.py --role planning) | High uncertainty, needs research |
| **Panel first** (launch.py --role panel) | Open-ended, needs diverse perspectives |

**Recommended for this project:** [Which option and why]

---

## 8. Notes & Decisions

*Running log of decisions, scope changes, and lessons learned during execution. Kept brief — one line per entry.*

| Date | Decision/Note |
|------|--------------|
| [date] | [What was decided and why] |

---

*Envelope version: 1.0 — [date]*
