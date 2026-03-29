# Brief — [Title]

**Scope:** [One sentence — what this brief delivers]
**Branch:** `feature/[name]` — new worktree
**Effort estimate:** S (< 30 min) / M (< 1 hour) / L (~2 hours) / XL (~4 hours) / XXL (~8 hours) / EXTREME (8-24 hours)
*Note: These are AI agent execution times. Agents work ~5x faster than humans on coding tasks.*
**Risk:** Low / Medium / High
**Affects:** [Which files/systems are modified]
**Project:** [PRJ-NNN if part of a multi-brief project, or "standalone"]

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] [Required tool/runtime] is available: `command --version`
- [ ] [Required library] is installed: `import X` or `which X`

### Credentials & Access
- [ ] [API/service] credentials at [path]: verified with [test command]

### Verification Capability
- [ ] Can verify deliverables via: [test command / screenshot tool / API call]
- [ ] If not available, first task is establishing verification

### Human Dependencies
- [ ] None — fully autonomous
  OR
- [ ] [Specific item] — needed before [specific phase]. Concentrated in [section].

---

## 1. The Problem (Why)

[What user-facing problem does this solve? What's wrong or missing today? Why does this matter?]

---

## 2. The Solution (What)

[Describe what will be built. Be specific enough that an agent can implement it without guessing at intent, but don't over-specify implementation details that the agent should decide.]

### 2.1 [Component/Feature A]
[Details]

### 2.2 [Component/Feature B]
[Details]

---

## 3. Design Alignment

[How this aligns with project goals and guidelines.]

<!-- Optional sections — remove or adapt based on your project type:
- **Dual emotional state:** [How does this contribute to calm/intense modes?]
- **User experience:** [How does this improve the end-user experience?]
- **Technical quality:** [Does this use the tech stack effectively?]
-->

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** [POC / Architecture / Alpha / Beta / Production — from `.cpo/lifecycle.md`]

**Stage-appropriate work in this brief:**
<!-- List what in this brief is appropriate for the current stage -->

**Out of scope for this stage:**
<!-- What actions are NOT allowed at this stage — from .cpo/lifecycle.md.
     If this brief touches items from a later stage, explain why and confirm CEO approval. -->

---

## 4. Implementation Plan

### Phase 1: [Name]
[What to build, what to test]

### Phase 2: [Name]
[What to build, what to test]

---

## 5. Parameters (if applicable)

| Parameter ID | Name | Type | Range | Default | What It Controls |
|-------------|------|------|-------|---------|-----------------|
| [id] | [name] | [slider/toggle/dropdown] | [min-max] | [default] | [description] |

---

## 6. Prerequisites (verify BEFORE building)

*What must be true before the executor writes a single line of code? If these aren't met, the code can't be tested.*

- [ ] [e.g., "Email provider configured: `curl -X POST https://api.resend.com/emails -H 'Authorization: Bearer $RESEND_API_KEY'` returns 200"]
- [ ] [e.g., "Database accessible: `psql $DATABASE_URL -c 'SELECT 1'` succeeds"]
- [ ] [e.g., "Test image exists at `tests/fixtures/test-image.jpg`"]

*If a prerequisite fails, STOP. Fix the prerequisite first or escalate to CPO. Do not build on a broken foundation.*

---

## 7. Acceptance Test (how we PROVE this works)

*A concrete, runnable test that proves the deliverables work. Not checkboxes — an actual command or scenario. The executor must run this and include the output as evidence.*

```bash
# Example acceptance test — replace with your brief's specific test:
# 1. Start the app
npm run dev &
sleep 5

# 2. [Test the specific thing this brief builds]
curl -X POST localhost:3000/api/[endpoint] \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}' \
  | python3 -m json.tool

# Expected: [describe what a passing response looks like]

# 3. Verify side effects
# [e.g., check database was updated, file was created, email was sent]
```

*If you cannot write a concrete acceptance test for this brief, the brief is too vague. Refine it before dispatching.*

---

## 8. Verification & Evidence

### Tests
| Test | What It Verifies | Level |
|------|-----------------|-------|
| [test name] | [what it proves] | [2/3/4] |

### Required Evidence (must be included in the PR)

*The supervisor MUST produce these artifacts and include them in the PR description. Without evidence, the PR should not be merged.*

| Evidence | Format | How to Produce |
|----------|--------|---------------|
| App health check | Terminal output | `curl localhost:PORT/api/health` |
| [Core flow test result] | Terminal output or screenshot | [specific command or Playwright script] |
| [Playwright screenshot of key page] | PNG file path | `python3 -c "from playwright..."` then Read the image |
| Test suite output | Terminal output | `npm test` or `python3 -m pytest` |

*Minimum: health check output + one core flow test. If the brief changes UI, include a Playwright screenshot.*

### Acceptance Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] Build succeeds (Level 1)
- [ ] App starts and health check passes (Level 2)
- [ ] Core flow works end-to-end (Level 3 — required for gate-relevant briefs)
- [ ] All required evidence produced and included in PR

---

## 9. What This Does NOT Include

[Explicitly list out-of-scope items to prevent scope creep]

---

## 10. Challenge Points

*Assumptions the executor should verify or push back on during implementation. Don't blindly follow the plan — if any of these turn out to be wrong, adjust and document why.*

- [ ] [Assumption 1 — what we assumed and why it might be wrong]
- [ ] [Assumption 2 — ...]
- [ ] [Assumption 3 — ...]

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| [risk] | [what goes wrong] | [how to handle] |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin <branch>`
2. `gh pr create --title "BL-NNN: <title>" --body "..." --base main --head <branch>`
3. State "WORK COMPLETE — PR created, ready for review"

The CPO or director then reviews and merges via `gh pr merge`.

---

## Convention: Autonomy Bias

**Bias towards full agent autonomy.** When this brief is part of a multi-brief execution:
- All human interaction points should be in ONE brief or ONE section, not scattered
- Prefer: human does setup -> agents run autonomously -> human reviews output
- Never: human intervenes at step 3, step 7, step 12 throughout a multi-brief execution
- If a human gate is unavoidable mid-execution: batch it with other gates at a natural break point

---

*Brief version: 1.0 — [date]*
