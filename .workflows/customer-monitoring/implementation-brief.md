# Customer Activity Monitoring — Implementation Brief

*Handover document for the agent implementing this workflow in a target project.*

---

## 1. What the Scaffolding Provides

The orchestration framework includes a complete workflow primitive. You have:

- **Directory structure:** `.workflows/customer-monitoring/` with `workflow.json`, `run.sh`, and `skills/`
- **Config format:** `workflow.json` defines steps, schedule, notifications, and artifact retention
- **Run script:** `run.sh` delegates to `tools/workflow_runner.py` which handles step execution, audit logging, artifact management, and registry updates
- **Enforced skill pattern:** Agent steps must invoke one of N terminal skills. 3-attempt retry with escalation fallback.
- **Scheduler:** `tools/workflow_scheduler.py` installs launchd plists (macOS) or crontab entries
- **Slack integration:** `tools/agent_slack.py` for posting reports to channels, DMs, and threads
- **Telegram integration:** `tools/agent_telegram.py` for CEO escalations
- **Dispatcher:** `tools/agent_dispatcher.py` with `.agent-comms/routing.json` for ad hoc inquiry routing

---

## 2. What Needs to Be Built

### 2a. Data Integration

**You must determine with the CEO:**
- Where do service logs live? (REST API endpoint, database, log files on a server)
- What authentication is needed? (API key, DB credentials, SSH key)
- What does an "activity event" look like? (Login, API call, feature usage, dashboard visit)
- Is there an existing endpoint that returns per-org activity counts, or do you need to parse raw logs?

**Expected output:** A Python function (stdlib-only if possible):
```python
def fetch_org_activity(config: dict) -> list[dict]:
    """Return activity data for all organizations.

    Each dict: {org_id, org_name, event_count_7d, event_count_30d, last_event_date}
    """
```

**Credential storage:** Follow the agent-telegram pattern — secrets at `~/.config/customer-monitoring/credentials.json` with 0600 permissions, never in repo.

### 2b. Classification Logic

Three states: **ACTIVE**, **DECLINING**, **INACTIVE**

Recommended starting thresholds (validate with CEO):
- **ACTIVE:** >= 50% of org's 30-day weekly average in the last 7 days
- **DECLINING:** < 50% of 30-day weekly average for 2 consecutive weeks
- **INACTIVE:** Zero events in the last 14 days

Edge cases:
- New orgs (< 30 days of history): use absolute thresholds instead of relative
- Excluded orgs: test accounts, internal use (list maintained in config)
- Seasonality: Finnish holidays, summer slowdown in July

**Expected output:**
```python
def classify_orgs(activity_data: list[dict], config: dict) -> list[dict]:
    """Classify each org as ACTIVE/DECLINING/INACTIVE.

    Each dict: {org_id, org_name, status, event_count_7d, trend_pct,
                last_event_date, notes}
    """
```

### 2c. Slack Output

**Channel:** A dedicated channel like `#customer-health` (to be created by CEO)

**Message format:**
```
INACTIVE (N orgs)
- OrgA: Last activity 18 days ago
- OrgB: Last activity 14 days ago

DECLINING (N orgs)
- OrgC: -62% vs 30d avg (was 45/week, now 17/week)
- OrgD: -48% vs 30d avg (was 30/week, now 16/week)

ACTIVE: N orgs normal activity

Next check: Tomorrow 09:00
```

**Implementation:** Use `tools/agent_slack.py send` via subprocess, or Slack webhook (simpler: POST JSON to a URL, stdlib `urllib`). Webhook URL stored in credentials.

**Threading:** Create a weekly thread anchor on Monday, post daily updates as replies to keep the channel clean.

### 2d. Cron Schedule

- **Recommended:** Daily at 09:00 Helsinki time, weekdays only
- **Cron expression:** `0 9 * * 1-5`
- **Install:** `python3 tools/workflow_scheduler.py install --workflow-dir .workflows/customer-monitoring`

### 2e. Agent Step (Optional for MVP)

For MVP, the classification can be fully deterministic (script steps only). Add an agent step later when you want qualitative analysis, e.g.:
- "Org X has been declining for 3 weeks — should we flag this as urgent?"
- "Org Y went inactive but they mentioned a vacation in the last support ticket"

When adding the agent step, define terminal skills:
- `no-action` — data is as expected, no intervention needed
- `alert-slack` — post an alert with the agent's analysis
- `escalate-ceo` — high-value customer needs CEO attention

---

## 3. Questions the Implementing Agent Must Ask the CEO

1. **"What is the service/platform name and where are its logs?"** (API endpoint, database connection string, log directory path)
2. **"What authentication is needed to access the logs?"** (API key, DB credentials, OAuth token)
3. **"Can you list all 25 customer org IDs/names, or is there an endpoint that returns all orgs?"**
4. **"What Slack workspace and channel should receive the daily report?"** (Create `#customer-health` or use existing?)
5. **"What's the Slack webhook URL?"** (Create at api.slack.com/apps -> Incoming Webhooks, or use bot token from slack.json)
6. **"Are there any orgs to exclude from monitoring?"** (test accounts, internal use, demo accounts)
7. **"What does 'healthy' activity look like?"** (How many events/week is normal for a typical org?)
8. **"Is there any Finnish holiday calendar or seasonality to account for?"** (Helsinki business hours, July summer break, Christmas period)
9. **"Should the system send a Telegram alert to you for INACTIVE orgs, or is Slack sufficient?"**
10. **"Who is the sales lead's Slack handle?"** (for @-mentions on urgent items)

---

## 4. Definition of Done

### MVP (Phase 1)

- [ ] `fetch_org_activity()` function works and returns real data from the service
- [ ] `classify_orgs()` correctly labels all 25 orgs with reasonable thresholds
- [ ] Slack message posts to the correct channel with the format above
- [ ] System cron (launchd) runs daily at 09:00 and produces output
- [ ] Sales lead confirms the Slack message is readable and actionable
- [ ] No secrets committed to the repo
- [ ] Workflow registered in `.workflows/registry.json`
- [ ] First 3 days of audit.log entries look reasonable

### Enhanced (Phase 2)

- [ ] Ad hoc inquiry route works in the dispatcher (sales lead can ask questions via Slack)
- [ ] Temporary agent spawns, investigates, and replies within 5 minutes
- [ ] Historical trend data stored locally for week-over-week comparison
- [ ] Telegram escalation to CEO for critical situations (org inactive > 21 days, top-5 customer declining)

### Intelligence (Phase 3)

- [ ] Anomaly detection (sudden drops vs gradual decline)
- [ ] Monthly summary report with trends
- [ ] Integration with customer feedback data
- [ ] Finnish holiday awareness (suppress false positives during known breaks)

---

## 5. Phased Approach

### Phase 1 — MVP (2-4 hours agent time)

1. CEO answers questions 1-7
2. Build `steps/collect_data.py` — fetches org activity from the data source
3. Build `steps/classify.py` — classifies orgs and writes `analysis.json`
4. Build `steps/send_report.py` — formats and posts to Slack
5. Update `workflow.json` with actual steps (remove agent step for MVP)
6. Test with real data, validate output with CEO
7. Install cron: `python3 tools/workflow_scheduler.py install --workflow-dir .workflows/customer-monitoring`

### Phase 2 — Ad Hoc Inquiries (1-2 hours agent time)

1. Create `inquiry-prompt.md` — system prompt for the inquiry agent
2. Add route to `.agent-comms/routing.json` for the sales lead
3. Test end-to-end: sales lead sends Slack message -> dispatcher spawns agent -> agent reads workflow artifacts -> agent investigates -> reply posted to Slack

### Phase 3 — Intelligence (4-8 hours, lower priority)

1. Historical data storage (JSONL per org, one entry per day)
2. Week-over-week trend analysis
3. Anomaly detection (sudden drops get higher urgency)
4. Monthly summary report posted to Slack with charts/tables
5. Integration with support ticket data if available
