# review-backlog

Review and manage the CPO backlog — a structured, filterable list of items approaching implementation.

## Usage

`/review-backlog` — List all items grouped by priority with status indicators
`/review-backlog add "title" --priority P1 --source ceo --category tooling` — Add a new item
`/review-backlog update BL-003 --status planned --notes "text"` — Update an item
`/review-backlog filter --status backlog --priority P1` — Filter view
`/review-backlog filter --project PRJ-002` — Filter by project
`/review-backlog projects` — List all projects with their briefs and status
`/review-backlog promote BL-001` — Move from backlog to planned
`/review-backlog defer BL-003 --reason "text"` — Defer with reason

## Instructions

You manage the backlog stored in `.cpo/backlog.json`. Read the file, perform the requested operation, and write it back if modified.

### Data location

`.cpo/backlog.json` — the single source of truth.

### Schema

Each entry has these fields:
- `id` — auto-incrementing `BL-NNN` (use `next_id` from the file, then increment it)
- `title` — short description
- `status` — one of: `proposed`, `backlog`, `planned`, `in-progress`, `done`, `deferred`
- `priority` — one of: `P0` (urgent), `P1` (important), `P2` (should do), `P3` (nice to have)
- `source` — where it came from: `vision`, `ceo`, `research`, `feedback`, `retrospective`, `advisor`
- `source_ref` — link or reference to the source document
- `category` — domain tag: `infrastructure`, `agent-lifecycle`, `communication`, `planning`, `tooling`, `documentation`
- `created` / `updated` — ISO dates (YYYY-MM-DD)
- `notes` — CPO's current understanding, blockers, dependencies
- `project` — (optional) `PRJ-NNN` reference if part of a multi-brief project

The file also has a top-level `projects` array:
- `id` — `PRJ-NNN`
- `name` — human-readable project name
- `status` — `planning`, `experiments`, `executing`, `testing`, `complete`
- `envelope` — path to the project envelope document (or null)
- `briefs` — array of `BL-NNN` IDs belonging to this project
- `created` — ISO date
- `notes` — brief description

### Command: `/review-backlog` (no arguments)

List all items grouped by priority (P0 first, then P1, P2, P3). For each item show:

```
[STATUS_ICON] BL-NNN: Title (source, category)
  Notes: ...
```

Status icons:
- `proposed` → `[?]`
- `backlog` → `[ ]`
- `planned` → `[>]`
- `in-progress` → `[~]`
- `done` → `[x]`
- `deferred` → `[-]`

End with a summary line: `Backlog: N | Planned: N | In-progress: N | Done: N | Deferred: N`

### Command: `/review-backlog add "title" --priority P1 --source ceo --category tooling`

1. Read `.cpo/backlog.json`
2. Create a new entry using `next_id` for the ID (format: `BL-NNN` zero-padded to 3 digits)
3. Set `status` to `backlog`, `created` and `updated` to today's date
4. Increment `next_id`
5. Write the file back
6. Confirm: `Added BL-NNN: "title" (P1, backlog)`

`--notes "text"` is optional. If not provided, leave notes as an empty string.

### Command: `/review-backlog update BL-NNN --status planned --notes "text"`

1. Read `.cpo/backlog.json`
2. Find the entry by ID
3. Update the specified fields. Any of `--status`, `--priority`, `--notes`, `--category`, `--source` can be provided.
4. Set `updated` to today's date
5. Write the file back
6. Confirm: `Updated BL-NNN: field1 → value1, field2 → value2`

### Command: `/review-backlog filter --status backlog --priority P1`

1. Read `.cpo/backlog.json`
2. Filter entries matching ALL provided criteria (AND logic)
3. Display the filtered list using the same format as the default list command
4. Any field can be used as a filter: `--status`, `--priority`, `--source`, `--category`

### Command: `/review-backlog promote BL-NNN`

1. Read `.cpo/backlog.json`
2. Find the entry by ID
3. Set `status` to `planned`, `updated` to today's date
4. Write the file back
5. Confirm: `Promoted BL-NNN to planned: "title"`
6. Remind: "A brief should be written for this item."

### Command: `/review-backlog defer BL-NNN --reason "text"`

1. Read `.cpo/backlog.json`
2. Find the entry by ID
3. Set `status` to `deferred`, `updated` to today's date
4. Append the reason to `notes`: `" | Deferred: reason"`
5. Write the file back
6. Confirm: `Deferred BL-NNN: "title" — reason`

### Command: `/review-backlog projects`

1. Read `.cpo/backlog.json`
2. List all projects from the `projects` array:

```
PRJ-NNN: Project Name (status)
  Briefs: BL-001 [x], BL-002 [~], BL-003 [ ]
  Envelope: path/to/envelope.md
  Notes: ...
```

3. End with summary: `Projects: N total | Planning: N | Executing: N | Complete: N`

### Command: `/review-backlog filter --project PRJ-NNN`

1. Read `.cpo/backlog.json`
2. Filter entries where `project` field matches the given project ID
3. Display using the standard list format

### Error handling

- If an ID is not found: `Error: BL-NNN not found in backlog`
- If required arguments are missing: show the usage for that command
- If the JSON file doesn't exist: `Error: .cpo/backlog.json not found. Create it first.`
