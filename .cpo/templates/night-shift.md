# Night Shift Brief — [Date]

<!--
  NIGHT SHIFT BRIEF TEMPLATE
  ==========================
  This brief is prepared by the CPO or outgoing shift to scope and constrain
  night shift work. The night shift agent must follow this brief exactly.

  How to use:
  1. Replace [Date] with the date (YYYY-MM-DD).
  2. List priority tasks in order — the night agent works top-to-bottom.
  3. Rules section defines hard constraints. Do not remove default rules;
     add project-specific rules as needed.
  4. Shutdown Checklist must be completed before the night agent ends its session.
-->

## Priority Tasks

<!--
  Numbered list of tasks for the night shift, in priority order.
  Each task must have:
  - A clear, specific scope (what to do and where)
  - Acceptance criteria (how to know it's done)
  - Any relevant file paths, branch names, or references
  The night agent works through these in order and stops when the shift ends.
-->

1.
2.
3.

## Rules

<!--
  Hard constraints for the night shift. The default rules below should always
  be included. Add project-specific rules as additional numbered items.
-->

1. **No Tier 2 work without approval.** Tier 2 tasks (architectural changes, new integrations, scope expansions) require explicit CPO or owner approval. If a Tier 2 item is encountered, skip it and log it as a blocker.
2. **No force pushes.** All pushes must be regular pushes. If a push is rejected, investigate and resolve — do not force push.
3. **Commit frequently.** Make small, atomic commits with descriptive messages. Do not accumulate large uncommitted changesets.
4. **Escalate blockers via Telegram.** If you hit a blocker that prevents progress on any priority task, send a Telegram message to the project owner immediately. Do not wait or silently skip.

## Shutdown Checklist

<!--
  Every item must be completed before the night agent ends its session.
  Check off each item (replace [ ] with [x]) as it's done.
-->

- [ ] **Commit all work.** No uncommitted or unstaged changes should remain. All work must be pushed to the remote.
- [ ] **Update shift handover.** Fill out the shift handover document (`.cpo/templates/shift-handover.md` or the active handover file) so the morning shift can pick up seamlessly.
- [ ] **Log capacity.** Add an entry to the capacity log (`.cpo/templates/capacity-log.md` or the active capacity log) recording tasks completed, duration, and blockers.
- [ ] **Send completion message.** Send a Telegram message summarizing what was accomplished, what's pending, and any blockers for the next shift.
