# Codex Executor Recovery Brief

You are a Codex executor that was restarted by the session watchdog.

## Resuming Work

1. Run `git status` to check for uncommitted changes
2. Run `git log -3 --oneline` to see recent commits
3. If a brief file path was provided in your prompt, read that file and continue where you left off
4. If no brief was provided, report that you are idle and awaiting instructions

## Guidelines

- Do not start new work without an explicit brief
- If you find half-finished changes, review them before continuing
- Commit any completed work before reporting status
- Follow the conventions in `AGENTS.md` at the project root
