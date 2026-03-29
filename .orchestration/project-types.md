# Project Type Configurations

*Reference for the setup agent when adapting the CPO (Chief Project Orchestrator) to different project types.*

**Important:** "CPO" is the system handle — it never changes. It appears in directory names (`.cpo/`), commands (`--role CPO`), tmux sessions, and all framework procedures. Only the **display title** adapts per project type. Agents should understand that "CPO" = the persistent orchestrator, regardless of the display title.

---

## Product Development (default)
- **Display title:** Chief Product Owner
- **Deliverable term:** "feature" or "component"
- **Decision examples:** new features, architecture changes, UX decisions
- **Review cadence:** weekly deliverable quality pass
- **Verification focus:** builds, tests, visual/functional evidence

## Marketing Campaign
- **Display title:** Chief Campaign Owner
- **Deliverable term:** "campaign" or "asset"
- **Decision examples:** new campaigns, channel strategy, messaging direction
- **Review cadence:** weekly campaign performance review
- **Verification focus:** content quality, audience metrics, A/B results

## Research Project
- **Display title:** Chief Research Officer
- **Deliverable term:** "experiment" or "study"
- **Decision examples:** new research directions, methodology changes
- **Review cadence:** weekly results review
- **Verification focus:** data quality, reproducibility, documentation

## Content Production
- **Display title:** Chief Content Officer
- **Deliverable term:** "piece" or "publication"
- **Decision examples:** new content series, editorial direction
- **Review cadence:** weekly content quality review
- **Verification focus:** editorial standards, engagement, consistency

## Custom
- Ask user for: display title, deliverable term, example decisions, review criteria
- The system handle remains "CPO" regardless of the chosen display title
