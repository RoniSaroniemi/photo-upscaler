# Orchestration Use Cases — Prioritized Analysis

*Date: 2025-03-25*
*Context: CEO/CTO sparring session on where to apply the orchestration framework beyond product development*

---

## Company Context & Constraints

- **Stage:** 2-founder startup, 25 customers in Finland
- **Product:** Automated customer satisfaction/experience management for marketing and IT agencies (reduces client churn)
- **Current phase:** v1 → v2 refactor of core microservices. Product not yet at the level where marketing spend converts reliably — only early adopters.
- **Sales:** One non-technical sales lead. No active marketing until v2 is ready.
- **Tools:** ClickUp for project management, fragmented Google Drive docs for strategy/PMF thinking
- **Critical path:** v2 completion. CEO time is the bottleneck for everything.

### Key Principle

Every hour spent on orchestration setup is an hour not spent on v2. Implementations must either (a) run autonomously after setup, freeing CEO time, or (b) directly accelerate the v2 critical path.

---

## Scoring Dimensions

Each use case is scored 1-5 on five dimensions, weighted by current situation:

| Dimension | Weight | What it measures |
|---|---|---|
| Business value | High | Revenue impact, strategic importance |
| Setup effort | High | Inverse of CEO time required (5 = very easy) |
| Framework fit | Medium | How well this maps to orchestration vs simpler alternatives |
| Time to value | High | How quickly it delivers first useful output |
| Critical path impact | High | Does it accelerate v2 or compete with it for CEO time (5 = accelerates) |

---

## Ranked Use Cases

### #1. Customer Activity Monitoring → Slack Alerts

**Score: 9.2/10**

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 5 | Directly protects revenue. We sell churn reduction — churning our own customers is existential |
| Setup effort | 5 | Simplest possible implementation: cron + log parser + Slack webhook |
| Framework fit | 4 | Doesn't need full orchestration — single agent with heartbeat is enough |
| Time to value | 5 | Days. First useful Slack message could land within a single work session |
| Critical path impact | 5 | Zero drag on v2. Runs completely independently once set up |

**What it does:** A cron job checks our service logs, classifies organizations as active/inactive/declining, and posts a structured summary to Slack. Sales lead can act on it without touching any technical tooling.

**Why #1:** The asymmetry is enormous — a few hours of setup protects the entire revenue base indefinitely. At 25 customers, losing even 1-2 is a significant revenue hit. This is deterministic, low-risk, and immediately actionable.

**Right-sized orchestration:** No CPO/Director needed. Single agent, cron heartbeat, Slack output. ~10% of the framework's capability.

---

### #2. v2 Roadmap & Project Orchestration

**Score: 8.1/10**

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 5 | Accelerates v2 (our critical path), enables stakeholder communication |
| Setup effort | 3 | Needs upfront investment: define roadmap structure, orient CPO to repos |
| Framework fit | 5 | This is literally what the framework was built for |
| Time to value | 3 | ~1 week before it's meaningfully tracking and surfacing status |
| Critical path impact | 5 | Actively accelerates v2 by forcing decomposition and preventing thrashing |

**What it does:** A CPO agent maintains the v2 roadmap with planning docs living *in the repo* alongside code. Tracks what's briefed vs unbriefed, surfaces blockers, and generates stakeholder-ready status updates that can be forwarded to customers.

**Why #2:** The project structure currently lives in the CEO's head — that's a single point of failure. This reduces cognitive load of juggling a large refactor. Briefs become the contract between "what we decided" and "what we built," eliminating the classic mismatch where planning lives in one place and execution in another.

**Dual value:** Serves both internal planning and external stakeholder communication. Progress updates to customers ("what's coming in the next two weeks") become a byproduct of the system rather than a separate effort.

**Right-sized orchestration:** Start with CPO-only for planning/tracking. Expand to Director + teams when delegating implementation tasks. Full framework applies here.

---

### #3. Customer Feedback → v2 Priority Signal

**Score: 7.4/10** *(identified as blind spot during analysis)*

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 5 | Ensures v2 builds what customers actually need, not what we assume |
| Setup effort | 3 | Needs integration with support channels / ticket system |
| Framework fit | 4 | Periodic collection + analysis + structured output maps well to heartbeat pattern |
| Time to value | 3 | Depends on where customer feedback currently lives |
| Critical path impact | 4 | Directly informs v2 scope decisions |

**What it does:** An agent periodically pulls from support channels, categorizes feedback by theme, cross-references with the v2 roadmap, and flags misalignments. Example output: "3 of your top 5 customers have mentioned X, but it's not on the v2 plan."

**Why this matters:** We have 25 real customers giving real signals — support tickets, feature requests, complaints, usage patterns. If these aren't systematically flowing into v2 prioritization, we risk building a v2 that's technically better but misaligned with what customers actually want. This is a lighter, more tractable version of the PMF documentation problem.

**Right-sized orchestration:** Single agent with cron. Pull → analyze → report. Similar architecture to #1.

---

### #4. Customer Onboarding Tracking

**Score: 6.5/10** *(identified as blind spot during analysis)*

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 4 | Scales acquisition without proportional time investment |
| Setup effort | 3 | Needs defined onboarding checklist, integration with customer data |
| Framework fit | 3 | Simple state tracking + alerting, doesn't need deep orchestration |
| Time to value | 3 | Useful once onboarding process is codified |
| Critical path impact | 3 | Doesn't help v2 directly, but prevents new customer loss |

**What it does:** Tracks "customer X signed up 2 weeks ago, hasn't completed integration step 3, flag to sales lead." Catches customers who silently stall during onboarding — which is where early churn actually happens.

**Current priority:** Low urgency. Onboarding volume is manageable at current scale.

**Defer until:** Actively acquiring new customers again (post-v2 marketing push). Worth designing when the time comes.

---

### #5. Sales Pipeline Visibility

**Score: 5.8/10**

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 4 | Useful, but 25 customers + limited active deals means manageable scale |
| Setup effort | 2 | Where does sales data live? CRM? ClickUp? Email? Integration is the hard part |
| Framework fit | 3 | Aggregation + reporting, but depends on data source quality |
| Time to value | 2 | High if data is scattered, low if in one CRM |
| Critical path impact | 2 | Doesn't help v2. Takes CEO time to set up and maintain |

**What it does:** Aggregates deal status across sources, surfaces a clear picture of what's progressing and what's stalling.

**Core issue:** Sales lead can't run it, so CEO becomes the operator of a tool meant to help someone else. At current scale (25 customers, presumably single-digit active deals), the mental overhead of tracking pipeline is real but not overwhelming.

**Revisit when:** (a) Structured sales data lives in one place with an API, or (b) deal volume increases post-v2.

---

### #6. PMF / ICP Documentation System

**Score: 4.5/10**

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 5 | Potentially transformative — but only if the input problem is solved |
| Setup effort | 1 | Massive. Needs capture infrastructure, analysis framework, knowledge model |
| Framework fit | 3 | Analysis part fits; capture part doesn't — orchestration can't solve "founders don't write things down" |
| Time to value | 1 | Months before it's genuinely useful |
| Critical path impact | 1 | Competes directly with v2 for CEO time |

**What it does:** Collects scattered signals about product-market fit (customer conversations, meeting notes, competitive observations), synthesizes them, and tracks when new arguments contradict earlier ones.

**Why it ranks low despite being "the most important":** The bottleneck isn't analysis — it's input. An agent that brilliantly analyzes fragmentary, contradictory, incomplete information produces confident-sounding garbage. The hidden knowledge in founders' heads is the real repository, and no cron job can extract it.

**The path forward (but not now):** This becomes viable *after* solving the capture problem. Once meeting transcription is in place, customer feedback flows in via #3, and key decisions are documented via #2's roadmap process — the inputs exist for an agent to synthesize. This is the capstone, not the foundation.

---

### #7. Admin Automation

**Score: 3.8/10**

| Dimension | Score | Rationale |
|---|---|---|
| Business value | 2 | Small time savings per task, cumulative but slow |
| Setup effort | 3 | Per-task: some trivial, some not worth it |
| Framework fit | 1 | Orchestration is overkill. Simple scripts or one-shots are better |
| Time to value | 4 | Individual tasks can be fast |
| Critical path impact | 2 | Minor time recovery |

**Recommendation:** Don't build orchestration for this. When encountering a repetitive admin task, automate it with a quick script or Claude one-shot. No framework needed.

---

## Additional Blind Spots Evaluated

These were considered during analysis but did not rank high enough to include in the main list:

| Idea | Score | Reasoning |
|---|---|---|
| Competitive intelligence monitoring | ~4/10 | Useful strategically, but at current stage we know our competitors. Finnish market is small enough to hear things organically. Revisit when expanding beyond Finland. |
| Automated v2 regression testing | ~5/10 | Valuable, but this is standard CI/CD territory. If we don't have CI/CD, set that up instead — simpler and more reliable than agent orchestration. |
| Investor/advisor update generation | ~3/10 | At 2 founders with limited formal reporting, this saves ~2 hours/quarter. Not worth building. |

---

## Recommended Sequencing

```
Week 1:     #1 Customer Activity Monitoring
            (quick win, proves the pattern, protects revenue immediately)
                |
Week 2-3:   #2 v2 Roadmap Orchestration
            (highest sustained value, enables everything else)
                |
Month 2:    #3 Customer Feedback → v2 Priorities
            (once #2 gives a roadmap to map feedback against)
                |
Post-v2:    #4 Onboarding Tracking, #5 Sales Pipeline
            (when growth demands it)
                |
Eventually: #6 PMF Documentation
            (when capture infrastructure exists from #2 + #3)
```

**Key insight:** #1 and #2 are complements, not competitors. #1 is fast and proves the orchestration pattern works. #2 is the strategic investment that accelerates the critical path. Start #1 immediately, define structure for #2 in parallel, deploy #2 once the machinery is trusted.

---

## Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2025-03-25 | Initial analysis completed | CEO/CTO sparring session. Prioritized by value/effort ratio given v2 critical path constraint. |
| | | |
