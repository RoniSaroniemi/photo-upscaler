# Project Lifecycle

**Current stage:** POC
**Stage entered:** [DATE]
**CEO gate status:** pending

## Stage Progression

```
POC → Architecture → Alpha (optional) → Design → Beta → Production
```

For full stage definitions, see `.cpo/research/project-lifecycle-enforcement.md`.

---

## Stage 1: POC — "Does this work?"

*Goal: Capture essential uncertainties and test or reduce them. POC code is always disposable.*

### Understanding
- [ ] What is the core value proposition? (one sentence)
- [ ] What are the 1-3 biggest unknowns/risks?
- [ ] Which pillar contains the most uncertainty? → That pillar gets the first experiment.

### Exploration
- [ ] Competitive landscape researched? → Use `/browser-navigate` to screenshot competitors
- [ ] Technical approaches to evaluate? → If multiple options, launch a panel (`--role panel`)
- [ ] Referenced tools/APIs/services validated? → For each unvalidated one, write an experiment brief

### Experiments
- [ ] For each uncertainty: write a time-boxed experiment brief (max 2 hours)
- [ ] Each experiment produces a GO/NO-GO answer with evidence
- [ ] Experiments completed and results documented

### POC Build
- [ ] Minimum demo built that proves the core works (NOT a full app — just the critical path)
- [ ] Demo verified: it actually runs and produces the expected output

### Human Gate
- [ ] Findings presented to CEO: what we learned, what works, what doesn't
- [ ] CEO EXPLICIT decision received. The CEO must say "proceed to [next stage]" or equivalent. Positive engagement (questions, doc requests, discussion) is NOT approval. If no explicit decision after presenting, ask: "Have you decided on the gate? Proceed / pivot / more work?" Do not advance without a clear answer.

### Allowed Actions
Research, experiments, throwaway prototypes, panels, cost benchmarks

### NOT Allowed
Production code, auth, payments, deployment, polished UI

### Recommended Tools
- **Panel** (`--role panel`) — evaluate multiple approaches
- **Browser-navigate** — competitive research
- **Strategic Advisor** — identify unknowns
- **Planning** (`--role planning --preset light`) — structure experiments

---

## Stage 2: Architecture — "Design the structure before building on it"

*Goal: Strategic structural decisions informed by POC results. Good architecture = less painful migrations later.*

### Structure Design
- [ ] Service structure decided? (monolith vs microservices, how many containers/services)
      → Use planning session (`--role planning --preset standard`) to design
- [ ] Data schemas defined? (flexible vs structured, entities, relationships)
- [ ] API contracts between components defined? (endpoints, request/response shapes)
- [ ] Major decisions with multiple viable approaches resolved?
      → For each: launch a panel or run a quick POC. Document as ADR.

### Architecture Validation
- [ ] Architecture supports expansion to Beta and Production pillars?
      (Adding auth later won't require restructuring? Adding payments won't break the data model?)
- [ ] Quick integration POC: do designed components actually connect?

### Documentation
- [ ] Architecture Decision Records written for each major choice
- [ ] System diagram: what connects to what
- [ ] Pillar table filled out (below): what enters at which stage

### Human Gate
- [ ] Architecture presented to CEO with ADRs and reasoning
- [ ] CEO EXPLICIT decision received. The CEO must say "proceed" or "approved." Positive engagement is NOT approval. If idle 2+ checks with no explicit decision, ask: "Have you decided on the gate?" Do not advance without a clear answer.

### Allowed Actions
Schema design, API contracts, scaffold generation, ADR writing, integration POCs

### NOT Allowed
Feature code, UI beyond wireframes, auth/payment integration

### Recommended Tools
- **Planning** (`--role planning --preset standard`) — design the architecture
- **Panel** — debate major architectural choices
- **SWOT** (`/swot`) — assess chosen architecture risks and tradeoffs

---

## Stage 3: Alpha — "Core features only" (optional — skip for small projects)

*Goal: Build the very core features with production-quality logic on the architecture from Stage 2. Nothing extra.*

### Core Build
- [ ] Critical-path features identified (the minimum that demonstrates the product)
      → Write briefs ONLY for these. Nothing else.
- [ ] If 3+ briefs: **create a project envelope** before dispatching (brief dependencies, integration plan, E2E test)
- [ ] Built with production-quality logic (not throwaway like POC)
- [ ] Built on the architecture from Stage 2 (expandable to beta and production)

### Integration
- [ ] Core components work together end-to-end
- [ ] `/verify` run — app starts, core flow works, evidence captured

### Human Gate
- [ ] Core flow demoed to CEO: "Here's the product working end-to-end, core features only"
- [ ] CEO EXPLICIT decision received. Positive engagement is NOT approval. If idle 2+ checks, ask: "Have you decided on the gate?" Do not advance without a clear answer.

### Allowed Actions
Core feature code, basic UI, automated tests for core features

### NOT Allowed
Auth, payments, deployment to production, performance optimization

### Recommended Tools
- **Director** — if 4+ briefs
- **Meta-learner** (`--observe`) — observe the first real build cycle
- **Browser-navigate** / `/verify` — verify core UI flow

---

## Stage 4: Design — "How should this look and feel?"

*Goal: Discover and codify the product's visual identity, UX patterns, and design language through competitive research, CEO alignment, and iterative mockups. This stage has the HIGHEST human involvement — frequent review cycles, not a single gate.*

*Note: This stage is most relevant for user-facing products. For backend-heavy or data projects, this may focus on data schema design, API design, or dashboard layout instead of visual UI. Adapt the checklist to what "design" means for your project.*

### Competitive Research
- [ ] Screenshot 5-10 competitors using `/browser-navigate`
- [ ] Document for each: what works visually, what doesn't, pricing presentation, trust signals
- [ ] Identify 3-5 specific elements to adopt (e.g., "Let's Enhance's clean dark theme," "Upsampler's before/after slider")
- [ ] Identify 3-5 anti-patterns to avoid (e.g., "imgupscaler.ai's crossed-out prices and urgency badges")
- [ ] Present findings to CEO — "here's what the market looks like, here's what I recommend we borrow"

### CEO Preferences
- [ ] CEO provides initial direction: mood, feel, benchmarks they like
      → This may come as voice messages, screenshots, references — capture and document
- [ ] CEO identifies non-negotiables: "must feel honest/clean/professional/playful/etc."
- [ ] Document as `.cpo/design-direction.md` — the design brief that guides all iterations

### Style Exploration (iterative with CEO)
- [ ] Create 5-10 visual mockup variations using Playwright screenshots
      → These are real pages built with different CSS/layout approaches, not static images
      → Each variation should be viewable at a URL or captured as a screenshot
- [ ] Present variations to CEO — "here are 10 approaches, which direction resonates?"
- [ ] CEO narrows to 2-3 candidates
- [ ] Refine the candidates based on CEO feedback
- [ ] CEO picks the final direction
- [ ] **This is iterative** — expect 3-5 rounds of feedback. Do NOT treat this as a one-shot brief.

### Codification
- [ ] Extract the chosen style into reusable design tokens / CSS variables:
      → Colors, typography, spacing, border radius, shadows
      → Component patterns: buttons, cards, forms, headers
- [ ] Document as a mini style guide: `.cpo/design-system.md`
- [ ] Apply the codified style consistently across all pages
- [ ] Final Playwright screenshots of every page — CEO reviews for consistency

### Human Gate
- [ ] CEO reviews final styled product: "This looks like something I'd trust with my credit card"
- [ ] CEO EXPLICIT approval: "Design is locked. Proceed to Beta."
- [ ] CEO EXPLICIT decision received. Positive engagement is NOT approval. If idle 2+ checks, ask: "Have you decided on the gate?" Do not advance without a clear answer.

### Allowed Actions
CSS, layout changes, component styling, design tokens, mockup variations, Playwright screenshots, competitive research

### NOT Allowed
New features, backend changes, auth/payment logic changes, deployment

### Recommended Tools
- **Browser-navigate** — screenshot competitors AND your own variations
- **Panel** (`--role panel`) — evaluate design approaches from multiple perspectives
- **Playwright** — capture and compare variations systematically

---

## Stage 5: Beta — "First release feature set"

*Goal: Complete v1 feature set with the locked design applied. Architecture + business logic followed properly. Design at the level approved in Stage 4. Not hardened or optimized.*

### Feature Planning
- [ ] Complete v1 feature list defined (must-have vs nice-to-have)
      → Use `--role planning --preset standard` to structure briefs
- [ ] Which pillars activate at Beta? (check Pillar table below)
- [ ] **Project envelope created** (`.cpo/projects/<project>/envelope.md`) wrapping all briefs:
      → Brief dependency map (which briefs depend on which)
      → Integration test plan (how to verify briefs work together)
      → E2E test scenario (full user flow after all briefs merge)
      → When 3+ briefs exist, an envelope is MANDATORY. Do not dispatch briefs without one.

### Build
- [ ] All v1 features implemented (follow architecture from Stage 2)
- [ ] Design system from Stage 4 applied consistently
- [ ] Auth implemented (basic — e.g., magic link)
- [ ] Payments in sandbox/test mode
- [ ] UI matches the approved design direction from Stage 4

### Integration + Test
- [ ] Full end-to-end test passes (complete user flow)
- [ ] Playwright E2E screenshots of every step — compare against approved design
- [ ] Basic security scan (security horizontal)
- [ ] Strategic advisor review — any blind spots?

### Human Gate
- [ ] Beta presented to CEO: "All v1 features with approved design. Missing for production: [list]"
- [ ] CEO EXPLICIT decision received. Positive engagement is NOT approval. If idle 2+ checks, ask: "Have you decided on the gate?" Do not advance without a clear answer.

### Allowed Actions
All feature code, auth, sandbox payments, staging deploy, comprehensive testing

### NOT Allowed
Live payment processing, production deploy, marketing launch, design changes without CEO approval

### Recommended Tools
- **Director** — manages the full brief set
- **Planning** (`--role planning --preset standard`) — structure feature briefs
- **Security horizontal** — basic scan
- **Browser-navigate** / `/verify` — UI verification against approved design
- **SWOT** (`/swot`) — assess the beta

---

## Stage 6: Production — "Harden, polish, ship"

*Goal: Everything needed to go live. Hardening, security, final polish, live payments, production deployment.*

### Remaining Pillars
- [ ] Activate production-stage pillars:
      → Live payments (real Stripe, not sandbox)
      → Production deployment (Cloud Run, real domain)
      → Full monitoring and observability
      → Full security audit

### Hardening
- [ ] Security horizontal — full audit
- [ ] Full test suite (unit + E2E + Playwright)
- [ ] Error handling for all edge cases
- [ ] Rate limiting / abuse protection
- [ ] Input validation hardened

### Polish
- [ ] Visual fidelity to 100%
- [ ] Final UI review with CEO (Playwright screenshots)
- [ ] Copy/messaging review
- [ ] Performance optimization for key bottlenecks
- [ ] Quality-of-life features (nice-to-haves, with CEO approval)

### Ship
- [ ] Deploy to production
- [ ] Smoke test on production URL
- [ ] Monitoring active and verified
- [ ] Documentation: user-facing help, FAQ, terms
- [ ] CEO sign-off: "this is live"

### Learn
- [ ] Meta-learner report: what worked, what didn't
- [ ] SWOT of the project delivery
- [ ] Framework improvements identified
- [ ] Metrics report (if observability was running)

### Allowed Actions
Everything

### Recommended Tools
- **Security horizontal** — full audit before go-live
- **Browser-navigate** / `/verify` — final visual verification
- **Meta-learner** — observe deployment process
- **SWOT** (`/swot`) — post-launch assessment

---

## Project Pillars

*Fill during POC. Determines when each pillar enters the build.*

| Pillar | Uncertainty | POC Needed? | Architecture | Alpha | Beta | Production |
|--------|------------|-------------|-------------|-------|------|------------|
| [Core feature] | [H/M/L] | [Yes/No] | [Design] | [Build] | [Complete] | [Optimize] |
| [Frontend] | | | | | | |
| [Auth] | | | | | | |
| [Payments] | | | | | | |
| [Deployment] | | | | | | |
| [Monitoring] | | | | | | |

---

## Core Value Features (locked — human approved)

*Defined during POC or Architecture. CPO cannot build features outside this list without human approval.*

1. [to be filled]
2.
3.

## NOT core value (do not build until Beta, and only with human approval):
- [to be identified]

---

## Verification Levels

*Every verification claim must state which level was achieved. Lifecycle gates require Level 3.*

| Level | Name | What It Proves | Example |
|-------|------|---------------|---------|
| 0 | Exists | Files are present | `ls src/app/api/upload/route.ts` → exists |
| 1 | Compiles | Code has no syntax/type errors | `npm run build` passes, `tsc --noEmit` clean |
| 2 | Runs | App starts and responds to health checks | `npm run dev` + `curl localhost:3000/api/health` → 200 |
| 3 | **Flow works** | **Core user journey completes end-to-end** | Upload image → process → download result (actual file, not just HTTP 200) |
| 4 | Edge cases | Error paths, limits, and abuse scenarios handled | Invalid file type → proper error, oversized image → rejection, concurrent requests → no race condition |

**Level 0-1 is NOT verification — it's inventory counting.**
**Level 2 is the minimum for supervisor WORK COMPLETE.**
**Level 3 is required at every lifecycle gate.**
**Level 4 is required before Production stage.**

## Verification-Before-Expansion

*Before creating ANY new briefs at any stage:*

- [ ] Have you RUN the current build? (Level 2 minimum — app starts and health check passes)
- [ ] Have you TESTED the core user flow? (Level 3 — actual user journey, not just HTTP 200)
- [ ] Have you CAPTURED evidence? (Playwright screenshots, test output, API responses)
- [ ] Has evidence been REVIEWED? (by you, the director, or presented to human at gates)
- [ ] Has the human APPROVED expanding scope? (at stage gates)

**If any answer is NO → do not create new briefs. Verify first.**
**"Build passes" is Level 1. That is NOT sufficient.**
