# [PROJECT_NAME] Session Notes

## CPO Role

The CPO (Chief Project Orchestrator) for this project operates as **[DISPLAY_TITLE]**. "CPO" is the system handle used in all commands, paths, and configs. The display title reflects this project's domain.

## Telegram Comms

If you are acting as the CPO or you need to communicate with the project owner through Telegram, use the Telegram gateway skills in `.claude/skills/`:

- `/telegram-enable-communications`
- `/telegram-send-message`
- `/telegram-send-voice-message`
- `/telegram-read-messages`
- `/activitywatch-user-presence`

Project config is in `.agent-comms/telegram.json`.
Local bot secrets are in `~/.config/agent-telegram/accounts.json`.

For setup and troubleshooting, see `docs/telegram-agent-gateway.md`.
For local presence checks before messaging, see `docs/activitywatch-user-presence.md`.

## Slack Comms

For Slack communication, use the Slack gateway skills in `.claude/skills/`:

- `/slack-enable-communications`
- `/slack-send-message`
- `/slack-read-messages`
- `/slack-send-file`

Project config is in `.agent-comms/slack.json`.
Local bot secrets are in `~/.config/agent-slack/accounts.json`.

For setup and troubleshooting, see `docs/slack-agent-gateway.md`.

## Skill Library

For discovering and installing skills from other projects:

- `/skill-library list` — browse available skills
- `/skill-library search <keyword>` — search by keyword
- `/skill-library suggest` — get recommendations for this project
- `/skill-library show <name>` — view full skill details
- `/skill-library install <name>` — install a skill
- `/skill-library catalog <path>` — add a new skill to the catalog

Catalog location: `~/.config/orchestration/skill-library.json`
CLI tool: `tools/skill_library.py`

## Launching Agents

Use the unified launcher to start any agent role:

```bash
# Supervisor+executor pair
python3 tools/launch.py --role pair --brief <path> --branch <branch> [--provider claude|codex]

# Director + subconscious
python3 tools/launch.py --role director [--handover <path>] [--provider claude|codex]

# CPO + subconscious
python3 tools/launch.py --role cpo [--provider claude|codex] [--skip-comms]
```

This atomically creates sessions, launches providers, injects briefs, sets up cron loops, and verifies everything is running. See `.claude/skills/delegate/SKILL.md` for full usage.

`tools/delegate.py` still works as a backward-compatible wrapper for `--role pair`.

## Backlog Management

The CPO backlog tracks items approaching implementation — from vision items, CEO requests, research findings, and feedback. Use the `/review-backlog` skill to manage it:

- `/review-backlog` — list all items grouped by priority
- `/review-backlog add "title" --priority P1 --source ceo --category tooling` — add item
- `/review-backlog update BL-NNN --status planned --notes "text"` — update item
- `/review-backlog filter --status backlog --priority P1` — filter view
- `/review-backlog promote BL-NNN` — move to planned
- `/review-backlog defer BL-NNN --reason "text"` — defer with reason

Data: `.cpo/backlog.json`
Skill: `.claude/skills/review-backlog/SKILL.md`

## Workflows

Deterministic cron-driven processes live in `.workflows/`. Each workflow has its own directory with `workflow.json`, `run.sh`, and optional agent step skills. Workflows run on system-level cron (launchd/crontab), not Claude session crons.

- Registry: `.workflows/registry.json`
- Template: `.workflows/workflow-template/`
- Runner: `tools/workflow_runner.py`
- Scheduler: `tools/workflow_scheduler.py`
- Dispatcher: `tools/agent_dispatcher.py` with `.agent-comms/routing.json`
