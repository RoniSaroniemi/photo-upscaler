# Project Envelope: Honest Image Tools Beta v1

**Project ID:** PRJ-001
**Status:** executing
**Created:** 2026-03-29
**Briefs:** beta-01 (done), beta-02 (done), beta-03 (in progress), beta-04 (in progress), beta-05, beta-06, beta-07

---

## 1. Objective

Deliver a working photo upscaling web application where a user can: create an account via magic link, add funds via Stripe, upload an image (≤1024px), receive a 4x upscaled WebP result, see a transparent cost breakdown (compute + platform fee = total), and download the result. Free trial users get 1-2 upscales without an account.

This is the complete Beta — not individual features in isolation, but an end-to-end product that a real person can use. The CEO will review a live staging deployment at the Beta gate.

---

## 2. Experiments (Viability Probes)

All completed during POC stage:

| # | Question | Method | Result | Impact on Plan |
|---|----------|--------|--------|---------------|
| 1 | Can Real-ESRGAN run on Cloud Run? | POC container + deploy (PR #5) | **Yes** — $0.001-0.009/image | Proceed with CPU for ≤1024px |
| 2 | Do real photos match synthetic benchmarks? | 6 Unsplash photos on Cloud Run (PR #6) | **Partially** — ≤1024px OK, 1920px+ OOM | Cap at 1024px, GPU deferred to Production |
| 3 | Can we get per-request cost from GCP? | Cloud Monitoring + Logs research (PR #6) | **No native API** — formula-based via X-Processing-Time-Ms | Use `processing_seconds × $0.000116` |
| 4 | Neon DB connection from Cloud Run? | drizzle-kit push from local (post-PR #8) | **Yes** — 6 tables created, pooler works | Proceed with Neon |
| 5 | Resend API works? | curl test against API | **Yes** — 200 OK | Proceed with Resend |
| 6 | Stripe sandbox keys valid? | curl test against API | **Yes** — 200 OK | Proceed with Stripe |

No remaining viability questions — all external dependencies validated.

---

## 3. Brief Split

```
Phase A — Foundation (sequential, DONE):
  Brief 1: beta-01 Foundation + Database — L — Next.js scaffold, Drizzle, 6 tables in Neon [MERGED PR #8]
  Brief 2: beta-02 Production Inference — M — WebP output, validation, 2x/4x, error handling [MERGED PR #7]

Phase B — Auth + Payments (parallel, IN PROGRESS):
  Brief 3: beta-03 Auth System — L — Magic links via Resend, JWT sessions, rate limiting
  Brief 4: beta-04 Payments + Balance — L — Stripe Checkout, microdollar balance, webhooks

  *** INTEGRATION CHECK B: After merging 3+4, verify: ***
  - Auth flow creates user + balance row
  - Stripe webhook credits balance correctly
  - Session cookie persists across API calls
  - npm run build passes with both merged

Phase C — Core Pipeline (sequential):
  Brief 5: beta-05 Upload Flow + Core API — XL — Image upload, inference proxy, job management, GCS storage, cost calculation

  *** INTEGRATION CHECK C: After merging 5, verify: ***
  - Authenticated user can upload image and get job ID
  - Job polls show processing → complete transition
  - Cost breakdown in job response matches formula
  - Result exists in GCS bucket with signed URL
  - Balance deducted correctly
  - Failed upload returns no charge

Phase D — Frontend (sequential):
  Brief 6: beta-06 Frontend Pages + Free Trial — XL — Landing, pricing, account, upload UI, job status, free trial (1-2 per IP)

  *** INTEGRATION CHECK D: After merging 6, verify: ***
  - Full browser flow works: land → auth → add funds → upload → see cost → download
  - Free trial works without auth (1-2 per IP)
  - Pricing page shows formula and examples
  - Account page shows balance and transaction history

Phase E — Ship (sequential):
  Brief 7: beta-07 Deployment + CI/CD + E2E — L — Cloud Build, Cloud Run deploy (both services), IAM, Playwright E2E suite

  *** FINAL VERIFICATION: Full E2E on staging URL ***
```

### Dependency Graph

```
Brief 1 ──┬── Brief 3 (auth) ──┐
           │                    ├── Brief 5 (upload) ── Brief 6 (frontend) ── Brief 7 (deploy+E2E)
           ├── Brief 4 (pay)  ──┘
           │
Brief 2 ──────────── Brief 5 (upload — needs inference service)
```

---

## 4. Integration Plan

| Integration Point | Briefs Involved | What to Verify | How to Verify |
|-------------------|----------------|----------------|---------------|
| Auth → Balance creation | 3 + 4 | New user gets a balance row (0 microdollars) on first login | `psql: SELECT * FROM balances WHERE user_id = <new_user>` |
| Auth middleware → Upload API | 3 + 5 | Upload endpoint rejects unauthenticated requests (401), accepts valid session cookie | `curl -X POST /api/upscale` without cookie → 401; with cookie → 201 |
| Stripe webhook → Balance update | 4 + 5 | After Stripe checkout, balance increases; upload then deducts correctly | `stripe trigger checkout.session.completed` then check balance, then upload |
| Upload API → Inference service | 5 + 2 | Next.js proxies image to inference Cloud Run, receives WebP + timing header | Upload real image, verify response is WebP with X-Processing-Time-Ms |
| Upload API → GCS storage | 5 | Upscaled image stored in GCS bucket, signed URL works, auto-deletes after 24h | Upload, check `gsutil ls gs://honest-image-tools-results/`, download via signed URL |
| Upload API → Cost calculation | 5 + 4 | Actual cost = `(processing_ms/1000) × 116` microdollars + 5000 platform fee; balance deducted atomically | Upload, check job.totalCostMicrodollars matches formula, check balance decreased by exact amount |
| Frontend → All APIs | 6 + 3,4,5 | Browser UI hits all API endpoints correctly (auth, balance, upload, jobs, pricing) | Playwright: full user flow in browser |
| Free trial → Upload (no auth) | 6 + 5 | Unauthenticated upload works for first 1-2 per IP, then blocked | Upload twice without auth → success; third time → 403 with "create account" message |
| Cloud Run IAM → Inference | 7 + 2 | Frontend service can call inference service; public cannot | `curl` inference URL directly → 403; via frontend → 200 |
| CI/CD → Both services | 7 | Push to main triggers Cloud Build for both frontend and inference | `git push`, verify both services update on Cloud Run |

---

## 5. E2E Test Plan

**Scenario: Complete new user journey — free trial through paid upscale**

A user discovers the site, tries a free upscale, likes the result, creates an account, adds $5, and upscales a second image with full cost transparency.

### Verification Checklist

| # | Check | Expected | How to Verify |
|---|-------|----------|---------------|
| 1 | Landing page loads | Page renders with upload area and pricing info | Playwright: `goto('/')`, screenshot, check for key text |
| 2 | Free trial upscale (no auth) | Upload ≤1024px JPEG, get back WebP result + cost display ("would normally cost $X") | Playwright: upload file, wait for job complete, verify download link |
| 3 | Second free trial works | Same flow, succeeds | Playwright: upload again, verify success |
| 4 | Third free trial blocked | Returns "create account" prompt | Playwright: upload, verify 403/redirect to auth |
| 5 | Magic link auth | Enter email, receive magic link email, click link, redirected to account | Playwright + Resend API: submit email, fetch magic link from Resend logs or test recipient, navigate to link, verify session cookie set |
| 6 | Account page shows $0 balance | Balance displays "$0.00" with "Add funds" button | Playwright: check account page content |
| 7 | Add $5 via Stripe | Click "Add funds", select $5, complete Stripe Checkout with test card 4242... | Playwright: go through Stripe Checkout, verify redirect to success page |
| 8 | Balance updated to $5 | Account page shows "$5.00" | Playwright: check balance after webhook fires |
| 9 | Upload image (paid) | Upload ≤1024px image, see estimated cost, confirm | Playwright: upload, verify job created with estimated cost |
| 10 | Processing completes | Job status transitions pending → processing → complete within 60s | Playwright: poll job page, verify status changes |
| 11 | Cost breakdown displayed | Shows compute: $X.XXX, platform: $0.005, total: $X.XXX | Playwright: verify cost breakdown elements on job page |
| 12 | Download works | Signed URL returns WebP image | Playwright: click download, verify response is image/webp |
| 13 | Balance deducted correctly | Balance = $5.00 - total_cost | Playwright: check account page, verify new balance |
| 14 | Transaction history | Shows deposit ($5.00) and charge (-$0.XXX) with cost breakdown | Playwright: check account page transactions |
| 15 | Pricing page accurate | Shows formula, examples, and "honest pricing" messaging | Playwright: screenshot pricing page, verify content |
| 16 | Health check | `/api/health` returns OK with DB connection | `curl /api/health` → `{"status":"ok","db":"connected"}` |
| 17 | Inference health | Inference service `/health` returns OK | `curl <inference-url>/health` → `{"status":"ok","model_loaded":true}` |
| 18 | GCS cleanup | Uploaded results have 24h lifecycle | `gsutil lifecycle get gs://honest-image-tools-results/` confirms age:1 rule |

**Model/Cost:** Brief 7 executor uses Claude (not Codex) — Playwright E2E requires browser interaction and debugging.

---

## 6. Success Criteria

- [ ] All 7 briefs merged to main
- [ ] Integration checks B, C, D pass (verified after each phase merge)
- [ ] Full E2E test (checks 1-18 above) passes on staging URL
- [ ] CEO can personally complete the user journey on the staging URL
- [ ] No TypeScript errors (`npm run build` clean)
- [ ] No console errors in browser during E2E flow
- [ ] Cost calculation matches formula within 5% of actual Cloud Run billing
- [ ] Images auto-delete from GCS after 24 hours

---

## 7. Dispatch Strategy

**Director-managed with integration gates between phases.**

| Phase | Briefs | Parallelism | Gate Before Next Phase |
|-------|--------|-------------|----------------------|
| A | 1, 2 | Sequential | Build + schema push ✅ DONE |
| B | 3, 4 | Parallel (2 agents) | Integration check B |
| C | 5 | Sequential | Integration check C |
| D | 6 | Sequential | Integration check D |
| E | 7 | Sequential | Final E2E on staging |

CPO manages merges and runs integration checks between phases. No brief dispatches without the prior phase's gate passing.

**Recommended:** Direct CPO dispatch (not director) — only 5 remaining briefs, phased with gates. Director adds overhead without benefit at this scale.

---

## 8. Notes & Decisions

| Date | Decision/Note |
|------|--------------|
| 2026-03-29 | POC complete: GO at $0.001-0.009/image. CEO approved Architecture. |
| 2026-03-29 | Architecture: 10 ADRs. Hybrid (Next.js + FastAPI), Neon Postgres, microdollars, Resend, Stripe. |
| 2026-03-29 | CEO: cap at 1024px for Beta, GPU high-res is Production-stage (BL-001). |
| 2026-03-29 | CEO: $5 minimum deposit, 1-2 free per IP, Resend over Gmail. |
| 2026-03-29 | Planning session: 7 briefs, ~17h agent time, ~14h critical path. |
| 2026-03-29 | Brief 1 merged: BigInt default fix needed (drizzle-kit cannot serialize BigInt). |
| 2026-03-29 | Brief 2 merged: Production inference with WebP, 2x upscale (BL-002 delivered). |
| 2026-03-29 | Briefs 3+4 dispatched in parallel. |
| 2026-03-29 | GCS bucket created: gs://honest-image-tools-results/ with 24h lifecycle. |
| 2026-03-29 | CEO directive: project envelope mandatory for 3+ briefs. Created before Brief 5 dispatch. |
| 2026-03-29 | CEO directive: verify integration between briefs, not just within. Deliver working system at gates. |

---

*Envelope version: 1.0 — 2026-03-29*
