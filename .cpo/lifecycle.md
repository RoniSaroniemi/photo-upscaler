# Project Lifecycle

**Current stage:** Architecture
**Stage entered:** 2026-03-29
**CEO gate status:** POC approved (voice message, 2026-03-29 07:34 UTC). Architecture gate: pending.

## Stage Progression

```
POC → Architecture → Alpha (optional) → Beta → Production
```

For full stage definitions, see `.cpo/templates/lifecycle.md`.

---

## Stage 1: POC — "Does this work?"

*Goal: Can Real-ESRGAN run on Cloud Run at a viable cost (<$0.05 per image)?*

### Understanding
- [x] What is the core value proposition? (one sentence)
  → Honest, transparent photo upscaling at near-cost pricing — no subscriptions, no hidden markup.
- [x] What are the 1-3 biggest unknowns/risks?
  1. Can Real-ESRGAN run in a Cloud Run container within memory/CPU limits?
  2. What is the actual cost-per-image for inference? (target: <$0.05)
  3. What are cold start times, and are they acceptable for a pay-per-use model?
- [x] Which pillar contains the most uncertainty? → ML Inference (experiment dispatched)

### Exploration
- [x] Competitive landscape researched? → .cpo/research/competitive-landscape.md — zero competitors show cost breakdown
- [x] Technical approaches to evaluate? → .cpo/research/real-esrgan-feasibility.md — CPU+lightweight model for POC, GPU for production
- [x] Referenced tools/APIs/services validated? → Real-ESRGAN works on Cloud Run, cost confirmed viable

### Experiments
- [x] For each uncertainty: write a time-boxed experiment brief (max 2 hours)
- [x] Each experiment produces a GO/NO-GO answer with evidence → GO, $0.001-$0.009/image
- [x] Experiments completed and results documented → poc/benchmark-results.md

### POC Build
- [x] Minimum demo built that proves the core works → FastAPI + Real-ESRGAN on Cloud Run (PR #5 merged)
- [x] Demo verified: it actually runs and produces the expected output → 9 benchmark runs across 3 image sizes

### Human Gate
- [x] Findings presented to CEO: what we learned, what works, what doesn't
- [x] CEO decision: proceed to Architecture (approved via voice message 2026-03-29)

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

*Goal: Strategic structural decisions informed by POC results.*

### Structure Design
- [x] Service structure decided? → ADR-001: Hybrid (Next.js + separate FastAPI inference service)
- [x] Data schemas defined? → Postgres via Neon (ADR-002), full schema in docs/architecture.md
- [x] API contracts defined? → REST API with 4 endpoint groups (auth, balance, upscale, pricing)
- [x] Major decisions resolved? → 7 ADRs written, all decisions made

### Architecture Validation
- [ ] Architecture supports expansion to Beta and Production pillars?
- [ ] Quick integration POC: do designed components actually connect?

### Documentation
- [x] Architecture Decision Records written → ADR-001 through ADR-007 in docs/architecture.md
- [x] System diagram → ASCII diagram in docs/architecture.md
- [x] Pillar table filled out → Pillar table in docs/architecture.md

### Human Gate
- [ ] Architecture presented to CEO with ADRs and reasoning
- [ ] CEO decision: approve architecture / adjust / more POC needed

### Allowed Actions
Schema design, API contracts, scaffold generation, ADR writing, integration POCs

### NOT Allowed
Feature code, UI beyond wireframes, auth/payment integration

---

## Project Pillars

| Pillar | Uncertainty | POC Needed? | Architecture | Alpha | Beta | Production |
|--------|------------|-------------|-------------|-------|------|------------|
| ML Inference (Real-ESRGAN) | H | Yes — core experiment | Design container + API | Build | Complete | Optimize |
| Frontend (Next.js) | L | No | Design pages + upload flow | — | Build | Polish |
| Auth (magic link) | L | No | Design flow | — | Build | Harden |
| Payments (Stripe) | M | No — Stripe is proven | Design balance model | — | Build | Go live |
| Deployment (Cloud Run) | M | Yes — tied to inference | Design services | — | Build | Production |
| Monitoring | L | No | Design metrics | — | — | Build |

---

## Core Value Features (locked — human approved)

*Defined during POC or Architecture. CPO cannot build features outside this list without human approval.*

1. Upload image → upscale via Real-ESRGAN → download result
2. Transparent cost breakdown on every image (compute + platform fee = total)
3. Prepaid balance in real currency via Stripe (not credits)

## NOT core value (do not build until Beta, and only with human approval):
- Image restoration, inpainting, background removal (future tools)
- Subscription plans
- User accounts beyond magic link auth
- High-resolution support (1920px+/GPU) — CEO: Production stage only (BL-001)

---

## Verification-Before-Expansion

*Before creating ANY new briefs at any stage:*

- [ ] Have you RUN the current build? (not just committed — actually executed it)
- [ ] Have you TESTED every existing feature? (manual or automated, `/verify` recommended)
- [ ] Have you CAPTURED evidence? (Playwright screenshots, test output, API responses)
- [ ] Has evidence been REVIEWED? (by you, the director, or presented to human at gates)
- [ ] Has the human APPROVED expanding scope? (at stage gates)

**If any answer is NO → do not create new briefs. Verify first.**
