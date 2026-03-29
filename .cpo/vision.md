# Honest Image Tools — Vision

## Vision Statement

Give everyone access to advanced photo upscaling at transparent, near-cost pricing — no expensive software, no confusing subscriptions, no hidden markup.

## What We're Building

A suite of honest, no-BS image tools starting with photo upscaling. Users upload an image, it gets upscaled using Real-ESRGAN (self-hosted ML inference on Google Cloud Run), and they download the result. Every image shows its cost breakdown: compute cost + platform fee = total.

The pricing model is radically transparent: prepaid balance in real currency (not credits) via Stripe. Users pay what it actually costs plus a small, visible margin. No subscriptions, no tiers, no upsells.

Starting with upscaling. Future tools (restoration, inpainting, background removal) each stand alone and follow the same honest principles. Email magic link auth keeps it simple.

## Technology & Architecture

- **Frontend:** Next.js
- **Backend/Inference:** Python (FastAPI + Real-ESRGAN)
- **Hosting:** Google Cloud Run (self-hosted inference, cold start OK — optimize for cost)
- **Payments:** Stripe (prepaid balance)
- **Auth:** Email magic link
- **Testing:** Playwright for E2E verification
- **Infrastructure:** GCP project `photo-upscaler-24h` (billing linked, Cloud Run + Artifact Registry + Cloud Build APIs enabled)

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|---------------|
| Cost per upscale | Unknown | <$0.05 | Cloud Run billing + benchmarks |
| Cold start time | Unknown | <30s acceptable | Timing in POC experiments |
| Upscale quality | Unknown | Visually competitive | Side-by-side with competitors |

## Project Lifecycle

*Current stage and progression. Full checklist in `.cpo/lifecycle.md`.*

| Stage | Status | Key Focus |
|-------|--------|-----------|
| POC | **Active** | Validate Real-ESRGAN on Cloud Run, benchmark cost |
| Architecture | Pending | Design services, APIs, data model |
| Alpha (optional) | TBD | May skip for small project |
| Beta | Pending | Full feature set: auth, payments, upload flow |
| Production | Pending | Harden, deploy, go live |

## Key Principles

1. **Show the math** — cost breakdown on every image: compute + platform fee = total
2. **Self-hosted inference** — no third-party API markup
3. **Cold start is fine** — optimize for cost, not speed
4. **Delete by default** — images are temporary, not stored
5. **No dark patterns** — no subscriptions, no credits, no upsells
