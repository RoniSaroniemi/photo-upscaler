# Planning Brief: [Goal]

## Goal
[What needs to be planned — from the CEO or CPO]

## Known Constraints
[Budget, timeline, tech stack, team, etc.]

## Existing Context
[Links to vision docs, previous research, relevant skills in the library]

---

## Phase 0: Prerequisites Audit

Before any design work, the Planning Director must answer:

### Environment & Tools
- What programming languages, frameworks, or runtimes are needed?
- Are they installed? If not, can the agent install them?
- What development tools are needed (test runners, linters, build tools)?

### External Dependencies
- What APIs, services, or databases does this project connect to?
- Do we have credentials/access? Where are they stored?
- Is there a staging/test environment, or only production?

### Existing Solutions Check
- Run `/skill-library search` for relevant skills
- Check if other projects have solved similar problems
- Check if there are patterns in the skill library we can reuse
- What can we copy/adapt vs what must we build from scratch?
- **Search externally:** Are there open-source tools, libraries, or frameworks that solve part of this? Don't just re-read internal docs.

### Backlog Cross-Reference
- Read `.cpo/backlog.json` for related items
- Identify upstream dependencies (what must be done before this?)
- Identify downstream items this work unblocks

### Verification Capabilities
For each type of deliverable this plan will produce:
- [ ] Code: can we run it? Test it? What test framework?
- [ ] UI: can we verify visually? Screenshot tool available?
- [ ] API integration: can we make test calls? Staging endpoints?
- [ ] Data pipeline: sample data available? Can we run dry-runs?
- [ ] Configuration: can we validate? Can we test in isolation?

If any verification capability is missing, the FIRST brief must establish it.

### Human-Required Items
List everything that requires human action:
- [ ] [Item 1 — what's needed, who provides it, blocking which phase]
- [ ] [Item 2 — ...]

**All human items are resolved BEFORE agent work begins.**

---

## Phase 0.5: Human Setup Gate

Present all human-required items (from Phase 0) in ONE consolidated list. This gate exists to concentrate human interaction — no human dependencies should remain after this point.

- [ ] All human-required items from Phase 0 presented
- [ ] Human has resolved each item
- [ ] Agent has verified each resolved item (credentials work, access confirmed, etc.)

**Gate passes only when all prerequisites are resolved. No agent work proceeds until this gate clears.**

---

## Phase 0.7: Verification Capability Check

For each deliverable type identified in this plan, confirm the agent can verify its own output:

| Deliverable Type | Verification Method | Available? | If Missing: Action |
|-----------------|--------------------|-----------|--------------------|
| Code | Test runner (`[command]`) | Yes / No | First brief establishes test framework |
| UI | Screenshot tool / browser automation | Yes / No | First brief installs verification tooling |
| API integration | Test calls to staging endpoint | Yes / No | First brief sets up staging access |
| Data pipeline | Dry-run with sample data | Yes / No | First brief creates sample dataset |
| Configuration | Validation command (`[command]`) | Yes / No | First brief adds config validation |

**Rule:** If any verification capability is missing, the FIRST brief in the plan must establish that capability before any feature work begins.

---

## Autonomy Bias

**Bias towards full agent autonomy.** When splitting work into briefs:

- All human interaction points should be in ONE brief or ONE section, not scattered
- Prefer: human does setup -> agents run autonomously -> human reviews output
- Never: human intervenes at step 3, step 7, step 12 throughout a multi-brief execution
- If a human gate is unavoidable mid-execution: batch it with other gates at a natural break point

---

## Planning Director Guidance

**The Planning Director is a coordinator, not a doer.**
- For any phase requiring reading more than 3 files or investigating unknowns: delegate to the executor
- For research phases: always delegate. The executor should search externally (web, GitHub) not just re-read internal docs.
- For design decisions: include cost/ROI analysis where applicable
- **Challenge assumptions:** For each major decision, state the strongest counterargument. Don't produce plans that assume everything is correct.
- **Check the backlog** for related items at the start of planning

See `.director/planning-director-instructions.md` for full operating instructions.

---

## Planning Output Requirements

The Planning Director delivers a **Project Envelope** (`.cpo/templates/project-envelope.md`) containing:
1. Objective — what the complete set of briefs achieves
2. Experiments — viability probes with results (run before implementation briefs)
3. Brief split — ordered with dependency phases and parallel groups
4. Integration plan — cross-brief verification points
5. E2E test plan — the final validation scenario
6. Success criteria — how to know the project is truly done

Plus ready-to-dispatch briefs with:
- Verification sections referencing established capabilities
- A **"Challenge"** section: 2-3 assumptions the executor should verify or push back on during implementation
- `Project: PRJ-NNN` reference linking back to the envelope

The envelope becomes the director's operating manual for multi-brief execution.
