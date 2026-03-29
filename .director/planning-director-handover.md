# Planning Director Handover — Codex Adapter

**Date:** 2026-03-27
**Dispatched by:** CPO (Forge)
**Project root:** /Users/roni-saroniemi/Github/claude-orchestration

---

## Your Role

You are a **Planning Director** — NOT an execution director. Your job is to plan, not build. You produce ready-to-dispatch briefs that an execution director will later implement.

Read `.cpo/templates/planning-brief.md` for the planning pipeline template, then read your specific planning brief at `.cpo/briefs/planning-codex-adapter.md`.

## Your Planning Pipeline

Execute these phases in order:

### Phase 0: Prerequisites Audit
- Verify Codex CLI exists and works
- Test Codex in tmux (create session, launch, inject text, verify)
- Check skill library for relevant existing patterns
- Identify human-required items
- **Output:** prerequisites checklist

### Phase 0.5: Human Setup Gate
- If any prerequisites require human action, list them
- **Output:** human items list (or "none — fully agent-resolvable")

### Phase 0.7: Verification Capability Check
- Can we verify Codex works in tmux? (test it)
- Can we verify a supervisor communicates with a Codex executor? (test it)
- Can we verify budget/usage tracking? (investigate)
- **Output:** verification strategy

### Phase 1: Scope & Decompose
- What are the distinct components to build?
- How do they depend on each other?
- **Output:** component list with dependencies

### Phase 2: Research
- Read `evidence/multi-provider-investigation.md` for existing findings
- Read `evidence/permissions-investigation.md` for cross-provider config insight
- Check how the current director-instructions.md launches executors — what needs to change for Codex?
- Delegate research to your executor if you need deeper investigation
- **Output:** research summary

### Phase 3: Codebase Impact Analysis
- What existing files need modification? (session-manifest.json schema, director-instructions.md, dispatcher, watchdog)
- What new files are needed?
- What interfaces change?
- **Output:** impact map

### Phase 4: Modularity & Flexibility Assessment
- Where does provider selection need to be configurable?
- What's hardcoded as "claude" that should be parameterized?
- Should the manifest support a `provider` field per session?
- **Output:** flexibility flags with recommendations

### Phase 5: Design
- Open questions from the planning input (how does supervisor communicate with Codex? how to detect completion? how to handle skills gap?)
- Design decisions with rationale
- **Output:** design decisions document

### Phase 6: Reflect
- Gap analysis: what's missing?
- v1 vs v2 split: what's minimal viable?
- Risk assessment
- **Output:** reflection notes

### Phase 7: Brief Generation
- Write concrete briefs following `.cpo/templates/brief-template.md`
- Each brief has: scope, implementation plan, verification, acceptance criteria
- Include the Phase 0.7 verification strategy in each brief
- **Output:** ready-to-dispatch briefs

## Your Executor

You have an executor in tmux session `exec-planning-dir`. Use it for:
- Running research commands (checking files, testing Codex in tmux)
- Investigating codebase impact
- Testing verification capabilities

Do NOT use it for implementation — you are planning only.

## Deliverables

Write all outputs to `.cpo/plans/codex-adapter/`:
- `00-prerequisites.md`
- `01-research-summary.md`
- `02-impact-analysis.md`
- `03-modularity-assessment.md`
- `04-design-decisions.md`
- `05-reflection.md`
- `06-briefs/` (directory with one brief per component)
- `07-planning-summary.md` (the final synthesis)

When complete, state: **"PLANNING COMPLETE — deliverables at .cpo/plans/codex-adapter/"**

## Operational Notes

- All agents use `claude --dangerously-skip-permissions`
- tmux send-keys reliability: sleep 2 + safety Enter after every injection
- You are a temporary director — you die when planning is done
- Do NOT merge anything to main — the CPO handles that
- Do NOT start implementing — only plan
