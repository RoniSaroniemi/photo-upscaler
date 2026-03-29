# Daily TODO — 2026-03-29

## Stage: Architecture → Beta transition

### Architecture (DONE)
- [x] Architecture doc with 10 ADRs — docs/architecture.md
- [x] Planning session stress-tested with multiple perspectives
- [x] Sub-cent pricing resolved → microdollars (BIGINT)
- [x] CEO decisions incorporated: $5 min deposit, 1-2 free per IP, 2x upscale option
- [x] Free trial, error handling, deployment ADRs added (008-010)

### Awaiting CEO Decision
- [ ] **Email provider:** Gmail vs Resend (risk escalation sent via Telegram)
- [ ] **Architecture gate approval** to proceed to Beta

### Beta Prerequisites (need from CEO before dispatch)
- [ ] Neon database: create account + project, provide DATABASE_URL
- [ ] Stripe test keys: sk_test_*, pk_test_*, webhook signing secret
- [ ] Email credentials: Gmail App Password OR Resend API key (depending on decision)
- [ ] All 3 provided as .env.local variables

### Beta Briefs Ready (7 briefs, ~17h total)
1. Foundation + Database Schema (L, ~2h) — sequential first
2. Production Inference Service (M, <1h) — parallel with 3,4
3. Auth System — Magic Links (L, ~2h) — parallel with 2,4
4. Payments + Balance — Stripe (L, ~2h) — parallel with 2,3
5. Upload Flow + Core API (XL, ~4h) — after 2,3,4
6. Frontend Pages + Free Trial (XL, ~4h) — after 5
7. Deployment + CI/CD + E2E (L, ~2h) — after 6
