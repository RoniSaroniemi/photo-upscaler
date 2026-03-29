# Solution Panel Personas

System prompts for the Solution Discovery Panel. The CPO (or Panel Director) selects 3-5 personas based on the challenge type.

## Persona Selection Guide

| Challenge Type | Recommended Panel |
|---------------|-------------------|
| **Technical architecture** | Moonshot + Speed Builder + Technical Architect + Risk Analyst |
| **Product direction** | Moonshot + User Advocate + Business Analyst + Compounding Strategist |
| **Go-to-market** | Speed Builder + Business Analyst + User Advocate + Risk Analyst |
| **Platform/infrastructure** | Compounding Strategist + Technical Architect + Speed Builder + Risk Analyst |
| **Creative/open-ended** | Moonshot + Compounding Strategist + User Advocate + Speed Builder |
| **High-stakes decision** | Risk Analyst + Business Analyst + Technical Architect + Compounding Strategist |

## The Personas

| Persona | File | Core Question |
|---------|------|---------------|
| Moonshot Thinker | `moonshot-thinker.md` | "What if we had no constraints?" |
| Speed Builder | `speed-builder.md` | "What's the fastest path to value?" |
| Compounding Strategist | `compounding-strategist.md` | "What builds on itself over time?" |
| Risk Analyst | `risk-analyst.md` | "What breaks? What's the downside?" |
| User Advocate | `user-advocate.md` | "What does the end user experience?" |
| Technical Architect | `technical-architect.md` | "What's the cleanest implementation?" |
| Business Analyst | `business-analyst.md` | "What's the ROI? What's the market?" |

## Usage

1. The Panel Director reads the challenge brief from the CPO
2. Selects 3-5 personas based on challenge type (use the guide above or judgment)
3. For each persona: spawns an agent with the persona's system prompt + the challenge brief
4. Each agent produces output following `panel-output-format.md`
5. Panel Director synthesizes after Round 1 (mini panel) or Round 2 (full panel)

## Mini Panel vs Full Panel

- **Mini Panel (2-3 personas, 1 round):** Some uncertainty about the approach. Perspectives help narrow options.
- **Full Panel (3-5 personas, 2 rounds):** Open-ended challenge. Round 2 adds cross-commentary where each panelist reacts to all others' perspectives.
