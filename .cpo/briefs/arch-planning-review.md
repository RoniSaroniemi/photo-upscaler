# Planning Brief: Architecture Review for Honest Image Tools

## Goal
Stress-test the architecture design (docs/architecture.md) before proceeding to Beta. The architecture was designed by a single agent — we need multiple perspectives to find gaps, risks, and improvements. Incorporate CEO feedback on open questions.

## Known Constraints
- **Timeline:** 24h test sprint (H1), 1 week for Beta (H2)
- **Tech stack:** Next.js, Python FastAPI, Google Cloud Run, Stripe, Neon Postgres
- **Budget:** MVP-first, minimize infrastructure costs
- **Stage:** Architecture → preparing for Beta. No feature code yet.
- **Resolution cap:** 1024px max input for MVP/Beta. GPU for 1920px+ is Production-stage only (BL-001).

## Existing Context
- **Architecture doc:** docs/architecture.md (7 ADRs, full API contracts, data model, system diagram)
- **POC results:** poc/benchmark-results.md, poc/real-photo-benchmark.md, poc/gcp-cost-measurement.md
- **Competitive research:** .cpo/research/competitive-landscape.md
- **Technical feasibility:** .cpo/research/real-esrgan-feasibility.md
- **Vision:** .cpo/vision.md
- **Lifecycle:** .cpo/lifecycle.md (Architecture stage)

## CEO Decisions on Open Questions
These have been resolved by the CEO and must be incorporated:

1. **Email provider:** Use Google account via CLI for programmatic email sending (low cost). NOT Resend or SendGrid.
2. **Minimum deposit:** $1-5, accounting for Stripe's 30-50 cent minimum processing fee
3. **Free trial:** 1-2 free upscales per IP address, then require deposit. Emphasize honest pricing over free samples.
4. **Sub-cent amounts:** Need resolution — API uses "cents" but costs are $0.003. Suggest millicents or decimal USD.

## What the Planning Session Should Review

### Architecture Risks
- Is the Hybrid architecture (ADR-001) the right call? Any issues with Next.js proxying to FastAPI?
- Is Neon Postgres (ADR-002) risky for a financial application? Should we go straight to Cloud SQL?
- Is $0.005 flat platform fee (ADR-004) viable? Revenue at various volume levels?
- Any security concerns with the magic link auth design (ADR-007)?

### Missing Pieces
- How does the Google CLI email approach work for magic links? What's the setup?
- How do we handle Stripe's minimum transaction fee vs our small amounts?
- What about CORS, rate limiting, abuse protection in the API design?
- Error handling strategy — what happens when inference fails mid-processing?
- How do we handle the sub-cent pricing in the data model and API?

### Implementation Complexity
- How many briefs will Beta need? Estimate the build effort.
- What's the critical path? What blocks what?
- Which parts can be parallelized?

### Cost Sustainability
- At what volume does this become profitable?
- What are the fixed costs (Neon, Cloud Run minimum instances, domain, etc.)?
- Is the pricing model sustainable long-term?

## Output Expected
1. Revised architecture recommendations (what to change, what to keep)
2. Risk assessment with mitigations
3. Brief plan for Beta implementation (how many briefs, phasing, dependencies)
4. Resolution of the sub-cent pricing question
5. Any ADRs that should be added or modified
