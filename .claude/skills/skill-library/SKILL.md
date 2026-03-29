---
name: skill-library
description: Discover, install, and manage cross-project skills from the shared catalog. Use to browse available skills, get recommendations for the current project, or add new skills.
---

# Skill Library

Manage the cross-project skill catalog at `~/.config/orchestration/skill-library.json`. All commands wrap `tools/skill_library.py`.

---

## /skill-library list [--domain X]

List all available skills. Optionally filter by domain tag.

```bash
python3 tools/skill_library.py list
```

With domain filter:
```bash
python3 tools/skill_library.py list --domain communication
```

Other filters:
```bash
python3 tools/skill_library.py list --type plug-and-play
python3 tools/skill_library.py list --project foxie-monitoring
```

Output columns: name, type, source project, domain tags.

---

## /skill-library search <keyword>

Search skills by keyword. Matches against name, description, and domain fields (case-insensitive).

```bash
python3 tools/skill_library.py search "telegram"
```

Example: searching "monitor" finds skills tagged with the `monitoring` domain and skills with "monitor" in their description.

---

## /skill-library show <name>

Show full details of a single skill: description, type, domain, source path, config requirements, timestamps.

```bash
python3 tools/skill_library.py show telegram-send-message
```

Use this before installing to understand what a skill does and whether it needs configuration.

---

## /skill-library install <name>

Install a skill from the catalog into the current project's `.claude/skills/` directory.

```bash
python3 tools/skill_library.py install "<name>" --target .claude/skills
```

**Behavior by type:**
- **plug-and-play**: Copies the skill directory. Ready to use immediately.
- **configurable**: Copies the skill directory and warns about required config variables. List each variable and explain what it needs. The agent or user must configure these before the skill works.
- **pattern**: Refuses to install. Instead, show the source path and explain that this is a reference pattern. Tell the agent to read the source SKILL.md and adapt the approach for this project.

---

## /skill-library suggest

Recommend skills from the catalog based on the current project's context. This is the most useful command for new project setup.

### How to generate suggestions

1. **Read project context.** Look for project type and domain signals in:
   - `CLAUDE.md` — project description, role definitions, communication setup
   - `.orchestration/project-brief-input.md` — explicit domain and project type (if it exists)
   - `.cpo/cpo-routine.md` — what the CPO does in this project (if it exists)

2. **Extract keywords.** Look for terms like: monitoring, communication, telegram, slack, pipeline, data, feedback, customer, presence, alerts, notifications.

3. **Query the catalog.**
   ```bash
   python3 tools/skill_library.py --json list
   ```

4. **Match and rank.** For each skill in the catalog:
   - **Exact domain match**: skill domain tag appears as a keyword in the project context (highest relevance)
   - **Partial match**: skill description contains project keywords (medium relevance)
   - **Type bonus**: `plug-and-play` skills rank higher than `configurable` for new projects; `pattern` skills are lower priority

5. **Filter already-installed skills.** Check `.claude/skills/` for skills that are already present. Exclude them from recommendations (or mark them as "already installed").

6. **Present top 5-10 recommendations.** For each, show:
   - **Name** and **type**
   - **Why it's relevant**: which project keywords matched which domain tags
   - **What it does**: one-line description
   - **Action needed**: "ready to install" for plug-and-play, "needs config: X, Y" for configurable, "reference only" for pattern

### Example output format

```
Suggested skills for this project:

1. telegram-send-message (plug-and-play)
   Matches: project uses Telegram communication
   → Send messages to the project owner via Telegram bot
   Action: /skill-library install telegram-send-message

2. customer-status (configurable)
   Matches: project involves monitoring, customer data
   → Check activity status of a customer organization via API
   Action: needs config (api_endpoint, credentials_path) before use

3. review-feedback (pattern)
   Matches: project handles customer feedback
   → Reference pattern for building feedback review workflows
   Action: read source at /path/to/review-feedback for adaptation ideas
```

---

## /skill-library catalog <path>

Add a new skill to the catalog from the given directory path.

### Steps

1. **Verify the path.** Check that `<path>/SKILL.md` exists.
2. **Read the SKILL.md.** Extract the description from the YAML frontmatter or first paragraph.
3. **Determine metadata.** Ask the agent (or infer) for:
   - **name**: derive from the directory name
   - **domain**: comma-separated tags (e.g., `communication,telegram`)
   - **type**: one of `plug-and-play`, `configurable`, or `pattern`
   - **config-required**: for configurable skills, list the variables
4. **Run the catalog command:**
   ```bash
   python3 tools/skill_library.py catalog "<path>" \
     --name "<name>" \
     --domain "<domains>" \
     --type "<type>" \
     --description "<description>" \
     [--config-required "<var1,var2>"]
   ```
5. **Confirm** the skill was added by running `show`:
   ```bash
   python3 tools/skill_library.py show "<name>"
   ```

---

## Notes

- The catalog lives at `~/.config/orchestration/skill-library.json` and is shared across all projects on this machine.
- Use `python3 tools/skill_library.py sync` to verify all source paths are still valid.
- All CLI commands support `--json` for structured output when you need to parse results programmatically.
- Skills are copied on install, not linked. Changes to the source after installation are not reflected.
