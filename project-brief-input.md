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

The world is full of image services that wrap someone else's API and charge 10-50x markup with dark-pattern pricing (crossed-out prices, urgency badges, confusing credit systems). We run the model ourselves, show the actual cost breakdown (compute + platform fee = total), and treat users like adults who can read a price tag.

Starting with image upscaling. Future tools: restoration, inpainting, background removal. Each stands alone. Each follows the same honest principles. No accounts needed for browsing — email magic link for auth, prepaid balance in real currency (not credits) via Stripe.

## Roadmap

- **H1 (24h test):** Working MVP — upload, upscale via self-hosted Real-ESRGAN on Cloud Run, pay-per-image, download. Before/after comparison. Transparent cost breakdown.
- **H2 (1 week):** Polish — professional controls, multiple scale factors, batch upload, deploy to production domain.
- **H3 (1 month):** Suite expansion — add restoration tool, "buy me a coffee" developer page, explore Lightning Network for micropayments.

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

This project serves two purposes: (1) build a real micro SaaS product, and (2) test the orchestration framework in a 24-hour end-to-end run.

Key infrastructure already set up:
- GCP project: photo-upscaler-24h (billing linked, Cloud Run + Artifact Registry + Cloud Build APIs enabled)
- GitHub repo: RoniSaroniemi/photo-upscaler
- Playwright installed for browser-based verification

Detailed project prep, vision, and competitor analysis are available at the orchestration framework project:
- Vision: claude-orchestration/.cpo/projects/test-24h-photo-upscaler/vision.md
- Prep: claude-orchestration/.cpo/projects/test-24h-photo-upscaler/project-prep.md

The CPO should read both documents before starting work. The prep doc contains the 10-brief lifecycle plan, tech stack decisions, competitor screenshots, and verification strategy.

Key principles:
1. Honest pricing — show compute + platform fee = total. No credits.
2. Self-hosted inference — Real-ESRGAN on Cloud Run. No API middlemen.
3. Email magic link auth — no passwords, no friction.
4. Prepaid balance in real currency — $5 minimum top-up via Stripe.
5. Delete by default — images are temporary.
6. Cold start is fine — optimize for cost, not speed.
