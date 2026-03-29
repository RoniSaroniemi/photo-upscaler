# Honest Image Tools — Roadmap

## Completed

| Project | Date | Outcome |
|---------|------|---------|
| Architecture design (7 ADRs) | 2026-03-29 | Hybrid arch, Neon Postgres, REST API, $0.005 platform fee. docs/architecture.md |
| POC: Real photo validation + GCP cost measurement | 2026-03-29 | <=1024px OK ($0.001-0.005), 1920px+ fails CPU. Formula-based cost. PR #6 merged. |
| POC: Real-ESRGAN container + Cloud Run benchmark | 2026-03-29 | GO — $0.001-$0.009/image, 10-75s CPU. PR #5 merged. |
| POC: Competitive research | 2026-03-29 | Zero competitors show cost breakdown. 10-20x cheaper than Let's Enhance. |
| POC: Technical feasibility research | 2026-03-29 | CPU+lightweight model viable for POC, GPU for production. |
| Framework setup | 2026-03-29 | Orchestration framework configured, lifecycle initialized |

## Current Sprint

| Project | Status | Priority | Owner |
|---------|--------|----------|-------|
| Architecture: email provider decision | Awaiting CEO | P0 | CEO |
| Architecture: planning review + ADR updates | Done | P0 | CPO |
| Beta: 7 briefs ready for dispatch | Blocked (needs credentials) | P0 | CPO |

## Horizons

| Horizon | Timeline | Goal |
|---------|----------|------|
| H1 (Now) | 24h test (2026-03-29) | POC — validate Real-ESRGAN on Cloud Run, benchmark cost-per-image |
| H2 (Next) | 1 week | Beta — complete feature set with auth, payments, UI (~80% fidelity) |
| H3 (Later) | 1 month | Production — harden, deploy, go live. Explore restoration as second tool |
