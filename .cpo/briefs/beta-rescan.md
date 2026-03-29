# Supervisor Brief — Beta Rescan: Fix All Integration Issues

**Branch:** `fix/beta-rescan`
**Executor session:** `exec-rescan`

## 1. The Problem

The Beta was declared complete based on superficial checks (build passes, curl returns 200) without actually running the application end-to-end. A critical review found 12 unresolved issues. The Beta gate is BLOCKED until every issue is resolved and honestly verified.

This is NOT a "quick fix" brief — it's a complete rescan that must:
1. Identify every broken path
2. Fix each issue
3. Actually run the app and test every flow
4. Produce an honest assessment of what works vs what doesn't

## 2. Issues to Investigate and Fix

### Issue 1: Email auth missing env vars
The auth system uses Resend but `.env.local` may be missing `EMAIL_FROM` or the Resend email config. The auth code in `src/lib/auth/email.ts` needs to actually send emails. Verify:
- What env vars does the auth code expect?
- Are they all in `.env.local`?
- Does sending a magic link email actually work (test with Resend's `onboarding@resend.dev`)?
- Fix any missing env vars and update `.env.local` and `.env.local.example`

### Issue 2: Stripe webhook secret is "REPLACE_ME"
`.env.local` has `STRIPE_WEBHOOK_SECRET="REPLACE_ME"`. The webhook handler in `src/app/api/balance/webhook/route.ts` will fail signature verification.
- Install Stripe CLI if not present: `brew install stripe/stripe-cli/stripe`
- Run `stripe listen --forward-to localhost:3001/api/balance/webhook` to get a real `whsec_*` secret
- Update `.env.local` with the real secret
- Test: `stripe trigger checkout.session.completed` — does the webhook handler process it?

### Issue 3: GCS bucket not configured in env
The upload flow in `src/lib/storage/gcs.ts` needs a GCS bucket name. Check:
- What env var does the GCS code expect? (`GCS_BUCKET_NAME`? `GOOGLE_CLOUD_BUCKET`?)
- Is it in `.env.local`? The bucket exists: `gs://honest-image-tools-results/`
- Does the app have GCP credentials to access it locally? (`GOOGLE_APPLICATION_CREDENTIALS` or `gcloud auth application-default login`)
- Test: can the app actually upload to and generate signed URLs from the bucket?

### Issue 4: Free trial race condition
The free trial system tracks uses per IP hash. Check `src/app/api/upscale/route.ts` and `src/app/api/pricing/trial-status/route.ts`:
- Is there a race condition where two concurrent requests from the same IP could both pass the check?
- Fix: use a DB transaction with SELECT FOR UPDATE or an atomic increment
- Test: simulate concurrent requests (can use `Promise.all` with two fetch calls)

### Issue 5: Playwright tests never executed
Tests exist in `frontend/e2e/*.spec.ts` but were never actually run.
- Install Playwright browsers: `npx playwright install chromium`
- Start the dev server: `PORT=3001 npx next dev --port 3001`
- Run: `npx playwright test --project=chromium`
- Fix any failing tests
- Report: how many pass, how many fail, what's broken

### Issue 6: Cloud Build references non-existent secrets
`cloudbuild.yaml` references GCP secrets. Check:
- List all `secretManager` references in `cloudbuild.yaml`
- For each: does it exist in GCP Secret Manager? `gcloud secrets list --project=photo-upscaler-24h`
- Create any missing secrets or update cloudbuild.yaml to match reality
- Don't create secrets with real values — just verify the references are correct and document what needs to be created before deploy

### Issue 7-9: Verification was superficial
The previous integration checks verified HTTP status codes, not functionality. This rescan must:
- Actually submit forms in the browser (or via API with proper auth tokens)
- Verify data is written to the database after each operation
- Check that the inference service actually processes an image (not just returns 200)

## 3. Implementation Phases

### Phase 1: Environment Audit
1. Read ALL source files that reference `process.env.*` — compile a complete list of required env vars
2. Compare against `.env.local` — identify every missing or placeholder value
3. Fix `.env.local` with real values where possible, document what needs human action
4. Update `.env.local.example` to list ALL required vars
5. Create a `.env.check.ts` script that validates all required env vars are set on startup

### Phase 2: Fix Known Issues
1. Fix missing email env vars (Issue 1)
2. Set up Stripe webhook secret via Stripe CLI (Issue 2) — if Stripe CLI is available, otherwise document the manual steps
3. Add GCS bucket env var and verify GCP auth (Issue 3)
4. Fix free trial race condition with atomic DB operation (Issue 4)
5. Fix any other code issues discovered during env audit

### Phase 3: Run the App and Test Every Flow
Start the dev server and test each flow IN ORDER. For each, record: what happened, what worked, what broke.

1. **Health check:** `GET /api/health` — does DB connect?
2. **Pricing estimate:** `GET /api/pricing/estimate?width=1024&height=768` — correct cost?
3. **Free trial:** Upload an image without auth — does it work? Does it call inference? Does count decrement?
4. **Magic link auth:** POST to `/api/auth/send-magic-link` with your email — does Resend send the email? Can you click the link and get a session?
5. **Account page:** After auth, does `/account` show your email and $0 balance?
6. **Add funds:** Does Stripe Checkout session create? Can you complete with test card 4242...? Does webhook fire? Does balance update?
7. **Paid upload:** With balance, upload an image — does it go through the full pipeline? Inference → GCS → cost deduction?
8. **Job status:** Does `/jobs/:id` show the completed job with cost breakdown and download URL?
9. **Download:** Does the signed URL actually download the WebP image?

For steps that require the inference service (3, 7), check if `INFERENCE_SERVICE_URL` points to a live service. If the POC service has scaled to zero, it may need a wake-up request first.

### Phase 4: Execute Playwright Tests
1. Install browsers: `npx playwright install chromium`
2. Run all specs: `E2E_BASE_URL=http://localhost:3001 npx playwright test --project=chromium`
3. For each failing test: fix the test OR fix the app code (determine which is wrong)
4. Re-run until you have a clear count of passing vs failing
5. Tests that cannot pass without external services (Stripe, live inference) should be marked as skipped with a clear reason

### Phase 5: Honest Assessment
Write `poc/beta-rescan-report.md` with:
1. **Environment vars:** Complete list, which are set, which are missing, which need human action
2. **Each user flow:** What works, what doesn't, with evidence (error messages, screenshots if possible)
3. **Playwright results:** X pass, Y fail, Z skipped — with reasons for each failure
4. **Cloud Build:** Which secrets exist, which don't, what's needed before deploy
5. **Honest verdict:** "Beta is ready for staging deploy" or "These N things must be fixed first: [list]"

## 4. Verification

This brief's verification IS the honest assessment. No shortcuts:

```bash
# The rescan report exists and is honest
cat poc/beta-rescan-report.md

# Playwright was actually executed (test-results directory exists)
ls frontend/test-results/ 2>/dev/null || ls frontend/playwright-report/ 2>/dev/null

# .env.local.example lists ALL required vars
cat frontend/.env.local.example
```

## 5. What This Does NOT Include

- Do NOT deploy to Cloud Run — just verify locally
- Do NOT create real GCP secrets — just document what's needed
- Do NOT fix cosmetic/UI issues — focus on functionality
- Do NOT add new features
- Do NOT mark the Beta gate as passed — that's the CEO's decision after reading the report

---

## 6. Lifecycle Stage & Scope Lock

**Current lifecycle stage:** Beta (gate BLOCKED pending rescan)

**Scope lock:** Fix integration issues and produce honest verification. No new features, no scope expansion.

---

## If Your Executor Stalls

Kill and replace: `tmux -L photo-upscaler kill-session -t exec-rescan`

---

**IMPORTANT: When complete:**

1. Push branch and create PR with the rescan report and all fixes
2. Final message: **RESCAN COMPLETE — PR created with fixes and honest assessment**
3. Self-terminate
