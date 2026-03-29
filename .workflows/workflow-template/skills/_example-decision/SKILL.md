---
name: _example-decision
type: terminal
description: Example terminal skill for workflow agent steps. Replace with your actual decision skill.
---

# Example Decision Skill

This is a template for a terminal skill used in workflow agent steps. When the workflow runner invokes an agent for a qualitative decision, the agent MUST invoke one of the workflow's terminal skills before finishing.

## When to use

Describe the conditions under which this skill should be chosen.

## Output format

Write to `last-action.json`:

```json
{
  "skill": "_example-decision",
  "decided_at": "<ISO timestamp>",
  "reasoning": "<1-2 sentence explanation>",
  "confidence": 0.0,
  "data_summary": "<key data points that informed this decision>"
}
```

## Arguments

- `reasoning` (required): Why this action was chosen
- `confidence` (optional): 0.0-1.0 confidence score
- `data_summary` (optional): Key metrics or observations
