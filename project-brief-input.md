# Project Brief: Honest Image Tools

*Auto-setup brief for the Claude Orchestration Framework.*

---

## Identity

- **Name:** Honest Image Tools
- **Slug:** photo-upscaler
- **Type:** product
- **Display Title:** Chief Product Owner
- **Tech Stack:** Next.js, Python (FastAPI + Real-ESRGAN), Google Cloud Run, Stripe, Playwright

## Vision

Build a suite of honest, no-BS image tools — starting with upscaling — that give people access to advanced photo capabilities without expensive software, confusing subscriptions, or hidden markup. Self-hosted ML inference on Google Cloud Run, pay-per-use at near-cost pricing, radically transparent.

Starting with image upscaling. Future tools: restoration, inpainting, background removal. Each stands alone. Each follows the same honest principles. Email magic link auth, prepaid balance in real currency (not credits) via Stripe.

Key principles: (1) Show cost breakdown on every image — compute + platform fee = total. (2) Self-hosted inference. (3) Cold start is fine — optimize for cost. (4) Delete by default — images are temporary.

## Roadmap

- **H1 (24h test):** POC — validate Real-ESRGAN on Cloud Run, benchmark cost-per-image. Get the core working: upload → upscale → download.
- **H2 (1 week):** Beta — complete feature set with auth, payments, UI polish (~80% fidelity).
- **H3 (1 month):** Production — harden, deploy, go live. Explore restoration as second tool.

## Communication

### Telegram
- **Account:** forge_cpo_bot
- **Chat ID:** 8618118467

### Slack
- **Account:** skip

### Communication Mode
- **Mode:** local-poller

## Skills (Optional)

### Install from library
- browser-navigate

### Domains of interest
- communication

## Git

- **Remote:** https://github.com/RoniSaroniemi/photo-upscaler

## Additional Context

IMPORTANT: This project uses LIFECYCLE ENFORCEMENT. Read .cpo/lifecycle.md BEFORE creating any briefs. You start in POC stage. The POC goal is: "Can Real-ESRGAN run on Cloud Run at a viable cost (<$0.05 per image)?" Do NOT build auth, payments, or polished UI during POC. Focus on experiments and proving the core works.

Key infrastructure already set up:
- GCP project: photo-upscaler-24h (billing linked, Cloud Run + Artifact Registry + Cloud Build APIs enabled)
- GitHub repo: RoniSaroniemi/photo-upscaler
- Playwright installed for browser-based verification

Your first actions should be:
1. Complete the POC checklist in .cpo/lifecycle.md
2. Run experiments to validate core feasibility
3. Present findings to the CEO at the POC gate
4. Do NOT advance to Architecture or Beta without CEO approval

Detailed vision, prep docs, and competitor analysis are at the orchestration framework project:
- Vision: claude-orchestration/.cpo/projects/test-24h-photo-upscaler/vision.md
- Prep: claude-orchestration/.cpo/projects/test-24h-photo-upscaler/project-prep.md
