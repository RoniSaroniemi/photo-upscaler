# Supervisor Brief — Real E2E Testing Against Live Services

**Branch:** `fix/e2e-real-testing`
**Executor session:** `exec-e2e-real`

## 1. The Problem

The Beta was built across 7 briefs but ZERO end-to-end flows have been verified against real services. All credentials are now in place (DATABASE_URL, RESEND_API_KEY, STRIPE keys, STRIPE_WEBHOOK_SECRET, JWT_SECRET, GCS_BUCKET_NAME). We need to actually run the app and test every user journey with evidence.

## 2. The Solution

Start the dev server, test every user flow against real services, capture evidence (API responses, DB state, screenshots), fix any issues found, and produce an honest report.

## 3. Prerequisites

Before starting ANY testing:

1. Copy env file to frontend: `cp /Users/roni-saroniemi/Github/photo-upscaler/.env.local /Users/roni-saroniemi/Github/photo-upscaler/frontend/.env.local`
2. Add missing vars that the frontend needs but root doesn't have:
   - Ensure `GCS_BUCKET_NAME=honest-image-tools-results` is in frontend/.env.local
3. Push the DB schema: `cd frontend && source .env.local && DATABASE_URL="$DATABASE_URL" npx drizzle-kit push`
4. Install deps: `cd frontend && npm install`
5. Start dev server on port 3001: `PORT=3001 npx next dev --port 3001`

## 4. Test Flows — IN ORDER

For EACH flow, record: the exact command/action, the response, and evidence (JSON output, DB query result, or screenshot). If a flow fails, attempt to fix the code. If the fix is non-trivial (>15 min), document the issue and move on.

### Flow 1: Health Check
```bash
curl -s http://localhost:3001/api/health | python3 -m json.tool
```
Expected: `{"status":"ok","db":"connected"}`
**MUST see `"db":"connected"` — not `"db":"error"`.** If DB fails, stop and fix before continuing.

### Flow 2: Pricing (no DB needed)
```bash
curl -s "http://localhost:3001/api/pricing/estimate?width=1024&height=768" | python3 -m json.tool
curl -s "http://localhost:3001/api/pricing/formula" | python3 -m json.tool
```
Expected: correct microdollar cost breakdown

### Flow 3: Free Trial Status
```bash
curl -s http://localhost:3001/api/pricing/trial-status | python3 -m json.tool
```
Expected: `{"remaining":2,"total":2}`

### Flow 4: Magic Link Auth — Send Email
```bash
curl -s -X POST http://localhost:3001/api/auth/send-magic-link \
  -H "Content-Type: application/json" \
  -d '{"email":"YOUR_SIGNUP_EMAIL_HERE"}' | python3 -m json.tool
```
Replace YOUR_SIGNUP_EMAIL_HERE with the Resend account email (since onboarding@resend.dev can only send to the signup email).

Check the Resend dashboard (resend.com/emails) or inbox for the magic link email.
**Evidence needed:** show the API response AND confirm email was received (or check Resend dashboard for delivery status).

### Flow 5: Magic Link Auth — Verify Token
If email arrived, extract the token from the magic link URL and:
```bash
curl -s -v "http://localhost:3001/auth/verify?token=TOKEN_FROM_EMAIL" 2>&1 | grep -E "(Set-Cookie|Location|HTTP/)"
```
Expected: 302 redirect with `Set-Cookie: session=...`

If email did NOT arrive, use the DB to get the token:
```bash
source .env.local && psql "$DATABASE_URL" -c "SELECT token_hash FROM magic_link_tokens ORDER BY created_at DESC LIMIT 1"
```
Note: token_hash is a SHA-256 hash, not the raw token. If you can't verify via email, document this as a blocker.

### Flow 6: Account Page (with session)
Using the session cookie from Flow 5:
```bash
curl -s -b "session=JWT_FROM_COOKIE" http://localhost:3001/api/balance | python3 -m json.tool
```
Expected: `{"balance_microdollars":"0","formatted":"$0.00",...}`

### Flow 7: Stripe Add Funds
```bash
curl -s -X POST -b "session=JWT_FROM_COOKIE" \
  http://localhost:3001/api/balance/add-funds \
  -H "Content-Type: application/json" \
  -d '{"amount_cents":500}' | python3 -m json.tool
```
Expected: response with `checkout_url` pointing to Stripe Checkout.

**Do NOT complete the Stripe Checkout in browser** — just verify the session is created. To test the webhook:
```bash
# In a separate terminal, start stripe listen:
stripe listen --forward-to localhost:3001/api/balance/webhook

# In another terminal, trigger a test event:
stripe trigger checkout.session.completed
```
Check if the webhook handler processes it without errors.

### Flow 8: Free Trial Upload (no auth)
Find a small test image (use one from poc/test-images/ or download one):
```bash
curl -s -X POST -F "file=@/Users/roni-saroniemi/Github/photo-upscaler/poc/test-images/small-cafe.jpg" \
  http://localhost:3001/api/upscale | python3 -m json.tool
```
Expected: either a job response with status, or an error about inference service.
**Evidence needed:** the full response body.

If inference fails because the service is cold/down, document that. The POC service may need a wake-up:
```bash
curl -s https://esrgan-poc-132808742560.us-central1.run.app/health
```

### Flow 9: Playwright E2E Tests
```bash
cd frontend
npx playwright install chromium
E2E_BASE_URL=http://localhost:3001 npx playwright test --project=chromium --reporter=list
```
Record: how many pass, how many fail, failure reasons.

## 5. Evidence Report

Write `poc/e2e-real-report.md` with:

### For each flow:
- The exact command run
- The full response (truncated if >50 lines)
- PASS / FAIL / BLOCKED verdict
- If FAIL: the error message and root cause

### Summary table:
| Flow | Verdict | Notes |
|------|---------|-------|
| 1. Health + DB | ? | |
| 2. Pricing | ? | |
| 3. Free trial status | ? | |
| 4. Magic link send | ? | |
| 5. Magic link verify | ? | |
| 6. Account balance | ? | |
| 7. Stripe add funds | ? | |
| 8. Free trial upload | ? | |
| 9. Playwright tests | ?/34 pass | |

### Issues found and fixed:
List each issue, the fix applied, and verification.

### Issues found but NOT fixed:
List each with root cause and suggested fix.

### Honest verdict:
"These flows work: [list]. These don't: [list]. To unblock: [list]."

## 6. What This Does NOT Include

- Do NOT deploy to Cloud Run
- Do NOT create GCP secrets
- Do NOT add new features
- Focus on TESTING and FIXING, not building

---

## 7. Lifecycle Stage & Scope Lock

**Current lifecycle stage:** Beta (gate BLOCKED — real E2E testing)
**Scope lock:** Test and fix only. No new features.

---

**When complete:** Push branch with fixes + report, create PR, self-terminate.
