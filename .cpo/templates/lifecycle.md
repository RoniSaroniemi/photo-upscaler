# Project Lifecycle

**Current stage:** POC
**Stage entered:** [DATE]
**CEO gate status:** pending

## Stage Progression

```
POC → Architecture → Alpha (optional) → Beta → Production
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
- [ ] CEO decision: proceed to Architecture / pivot / more POC work

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
- [ ] CEO decision: approve architecture / adjust / more POC needed

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
- [ ] Built with production-quality logic (not throwaway like POC)
- [ ] Built on the architecture from Stage 2 (expandable to beta and production)

### Integration
- [ ] Core components work together end-to-end
- [ ] `/verify` run — app starts, core flow works, evidence captured

### Human Gate
- [ ] Core flow demoed to CEO: "Here's the product working end-to-end, core features only"
- [ ] CEO decision: proceed to Beta / adjust core / revisit architecture

### Allowed Actions
Core feature code, basic UI, automated tests for core features

### NOT Allowed
Auth, payments, deployment to production, performance optimization

### Recommended Tools
- **Director** — if 4+ briefs
- **Meta-learner** (`--observe`) — observe the first real build cycle
- **Browser-navigate** / `/verify` — verify core UI flow

---

## Stage 4: Beta — "First release feature set"

*Goal: Complete v1 feature set. Architecture + business logic followed properly. ~75-80% visual fidelity. Not hardened.*

### Feature Planning
- [ ] Complete v1 feature list defined (must-have vs nice-to-have)
      → Use `--role planning --preset standard` to structure briefs
- [ ] Which pillars activate at Beta? (check Pillar table below)

### Design
- [ ] User experience direction chosen (2-3 visual approaches → pick one)
      → Use Playwright screenshots for CEO review. Don't get stuck — MVP mindset.
- [ ] Key user flows documented step-by-step
      → For each flow: write a Playwright verification test

### Build
- [ ] All v1 features implemented (follow architecture from Stage 2)
- [ ] Auth implemented (basic — e.g., magic link)
- [ ] Payments in sandbox/test mode
- [ ] UI at ~75-80% visual fidelity

### Integration + Test
- [ ] Full end-to-end test passes (complete user flow)
- [ ] Playwright E2E screenshots of every step
- [ ] Basic security scan (security horizontal)
- [ ] Strategic advisor review — any blind spots?

### Human Gate
- [ ] Beta presented to CEO: "All v1 features, ~80% visual. Missing for production: [list]"
- [ ] CEO decision: proceed to Production / iterate / change direction

### Allowed Actions
All feature code, auth, sandbox payments, staging deploy, comprehensive testing

### NOT Allowed
Live payment processing, production deploy, marketing launch

### Recommended Tools
- **Director** — manages the full brief set
- **Planning** (`--role planning --preset standard`) — structure feature briefs
- **Security horizontal** — basic scan
- **Browser-navigate** / `/verify` — UI verification
- **SWOT** (`/swot`) — assess the beta

---

## Stage 5: Production — "Harden, polish, ship"

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

## Verification-Before-Expansion

*Before creating ANY new briefs at any stage:*

- [ ] Have you RUN the current build? (not just committed — actually executed it)
- [ ] Have you TESTED every existing feature? (manual or automated, `/verify` recommended)
- [ ] Have you CAPTURED evidence? (Playwright screenshots, test output, API responses)
- [ ] Has evidence been REVIEWED? (by you, the director, or presented to human at gates)
- [ ] Has the human APPROVED expanding scope? (at stage gates)

**If any answer is NO → do not create new briefs. Verify first.**
