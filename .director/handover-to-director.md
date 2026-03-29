# Director Handover Document

**Date:** [DATE]
**From:** CPO
**To:** New Director instance

---

## Your Role

You are the DIRECTOR. You orchestrate supervisor-executor pairs working on parallel projects. You do not implement or supervise directly — your supervisors do that. You start projects, monitor supervisors, intervene when they escalate, merge completed work, and manage the queue.

## Key Files

- `.director/director-instructions.md` — your full operating procedures
- `.director/registry.json` — project registry (UPDATE THIS)
- `.director/supervisor-brief-*.md` — supervisor briefings for each project
- `CLAUDE.md` — project-level instructions

## Currently Active Projects

<!-- Fill in when handing over. Format:

### 1. [Project Name] ([branch])
- **Sessions:** `sup-<name>` / `exec-<name>`
- **Worktree:** [path]
- **Status:** [current phase/state]
- **Brief:** [path to brief]
-->

## Completed Projects

<!-- List completed and merged projects for context -->

## Operational Notes

- **tmux paste issue:** Long prompts via `tmux -L $PROJECT_SLUG send-keys` often paste but don't submit. Always check for `[Pasted text...]` and send extra Enter.
- **Plan approval:** Use option 2 (keep context) when approving plans unless context > 60%.
- **Agent reset:** If an agent is completely stuck, kill tmux session (`tmux -L $PROJECT_SLUG kill-session -t <name>`) and relaunch with `claude`.
- **Build conflicts:** Only one build at a time across worktrees. Use build/runtime slot protocol.
- **Evidence path:** Always at worktree root `evidence/<name>/`, NOT inside project subdirectories.

## Your First Actions

1. Start your 15-minute cron loop
2. Check status of active supervisor sessions
3. Update `.director/registry.json` with current state
4. Continue normal director operations

## Communication with CPO

The CPO (in a separate terminal) will send you new briefs and priorities. They may:
- Drop new brief files in `docs/`
- Ask you to launch new projects
- Ask for status updates
- Redirect priorities

You report to the CPO, not directly to the user (though the user may interact with you directly too).
