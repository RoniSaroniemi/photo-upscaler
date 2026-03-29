# swot

Produce a structured SWOT analysis for any observed system, agent run, session, or process.

## Usage

`/swot <target>` — Analyze a target and write SWOT to default output path
`/swot <target> --output <path>` — Analyze a target and write SWOT to a specific file

## Target types

The `<target>` argument determines what data to collect before analysis:

### 1. Tmux session name

Example: `/swot advisor`

If `<target>` matches an active tmux session (check with `tmux has-session -t <target> 2>/dev/null`):
1. Capture the last 200 lines: `tmux capture-pane -t <target> -p -S -200`
2. Use the captured output as the raw data for analysis

### 2. File path

Example: `/swot .cpo/observations/raw-data.md`

If `<target>` is a path to an existing file:
1. Read the file contents
2. Use the file contents as the raw data for analysis

### 3. Run ID

Example: `/swot panel-20260328-143022-a1b2c3`

If `<target>` matches the pattern of a run ID (contains a timestamp-like segment) and a corresponding directory exists under `.cpo/runs/` or `.cpo/observations/`:
1. Read all files in the run directory
2. Use their combined contents as the raw data for analysis

### 4. Free text / concept

Example: `/swot "the backlog management system"`

If `<target>` is quoted text or doesn't match any of the above:
1. Use your knowledge of the project (read relevant files, check recent git history, review documentation) to gather context about the topic
2. Use the gathered context as the raw data for analysis

## Instructions

After collecting raw data based on the target type, apply the SWOT framework below and write the output.

### Output path

- If `--output <path>` is provided, write to that path
- Otherwise, write to `.cpo/observations/swot-<target-slug>-<YYYY-MM-DD>.md`
  - `<target-slug>`: lowercase, spaces/special chars replaced with hyphens, max 40 chars
  - Example: `.cpo/observations/swot-backlog-management-system-2026-03-28.md`

Create parent directories if they don't exist.

### Output format

Write the analysis in this exact format:

```markdown
# SWOT Analysis: <Target Title> — <YYYY-MM-DD>

**Observation period:** <describe what was observed and timeframe if applicable>
**Model:** <model name if known, otherwise omit>

---

## Strengths

<3-5 numbered points. Each point has a **bold lead sentence** followed by supporting detail. Be specific and evidence-based — reference actual data, files, behaviors, or outputs observed. No generic observations.>

## Weaknesses

<3-5 numbered points. Same format. What failed, underperformed, or is missing? Cite specific evidence.>

## Opportunities

<3-5 numbered points. Same format. What could be improved? What new capabilities would this enable?>

## Threats

<3-5 numbered points. Same format. What could go wrong at scale? What assumptions might break? What external risks exist?>

---

## Summary Assessment

<One paragraph overall assessment. Start with "**Overall:**" and give a concise verdict, then note the key gaps or priorities.>

**Recommended improvements:**
<Bulleted list of 3-5 specific, actionable improvements ranked by priority.>
```

### Quality requirements

- Every point must be **specific and evidence-based**. Reference actual files, outputs, metrics, or behaviors — not generic platitudes.
- Each SWOT section should have **3-5 points**. Fewer than 3 means you haven't looked hard enough. More than 5 means you should consolidate.
- **Strengths** and **Weaknesses** describe the current state. **Opportunities** and **Threats** describe future possibilities.
- The **Summary Assessment** should be a genuine verdict, not a wishy-washy "it's a mixed bag." Take a position.
- **Recommended improvements** should be concrete next steps, not restated weaknesses.

### After writing

1. Confirm the output path to the user
2. Show a brief summary (2-3 sentences) of the key findings
