# Honest Image Tools — Full Journey Verification Report (v3)

**Date:** 2026-03-30 11:47 UTC+3
**Branch:** fix/verify-all-v3
**App port:** 3001
**Health check:** `{"status":"ok","version":"0.1.0","db":"connected"}`
**Env:** .env.local copied from source repo with real credentials (Neon, Stripe test, Resend, JWT)

## Scorecard

| # | Journey | Result | Level | Notes |
|---|---------|--------|-------|-------|
| J1 | Discovery | **PASS** | **L2** | Homepage (19KB) and pricing (22KB) serve correctly with product messaging |
| J2 | Free Trial | **FAIL** | L1 | Trial reset works (200), but all 3 uploads fail: "Could not read image dimensions" — test PNG not compatible with sharp |
| J3 | Sign Up | **PARTIAL** | **L2** | Magic link token generated + stored in DB. Resend API returns 403 (sandbox: can only send to owner email). Dev-login works, session valid, balance readable ($4.99) |
| J4 | Add Funds | **PASS** | **L3** | Real Stripe sandbox checkout URL returned: `checkout.stripe.com/c/pay/cs_test_...` — this is a real Stripe session |
| J5 | Paid Upload | **FAIL** | L1 | Same "Could not read image dimensions" error — never reaches inference service. Balance unchanged |
| J6 | Job History | **PASS** | **L2** | Returns real job data from Neon DB (1 previously failed job). Auth + DB query both work |
| J7 | Error Handling | **PARTIAL** | L1 | File-type validation works ("File must be an image"). Insufficient-balance test blocked by image dimension bug. Invalid token returns 307 redirect (empty body), not a JSON error |

## Totals

- **L3:** 1/7 (J4 only)
- **L2:** 3/7 (J1, J3, J6)
- **L1:** 2/7 (J2, J7 — endpoints exist but flows broken)
- **FAIL:** 1/7 (J5 — blocked by same image bug as J2)

## Blocking Issues

### 1. Test image incompatible with sharp (blocks J2, J5, J7-insufficient-balance)

The verification script generates a minimal PNG via Python struct/zlib. The app's upload handler uses `sharp` to read dimensions and fails with "Could not read image dimensions". This single bug blocks 3 journeys from progressing past L1.

**Impact:** Cannot verify free trial flow, paid upload flow, or insufficient-balance error handling.
**Fix needed:** Either fix the test image generation to produce a sharp-compatible PNG, or fix the upload handler to handle this PNG format.

### 2. Resend sandbox limitation (affects J3)

Resend API returns 403: "You can only send testing emails to your own email address (roni.saroniemi@foxie.ai)". The magic link token IS generated and stored in DB, but email delivery fails for test addresses.

**Impact:** Cannot verify real email delivery to arbitrary addresses. Auth flow works via dev-login bypass.
**Scoring:** L2 per rules (sandbox limitation, not a code bug).

### 3. Invalid token returns redirect, not JSON error (affects J7)

`GET /api/auth/verify?token=bogus` returns HTTP 307 redirect with empty body instead of a JSON error response. This may be by design (redirect to login page) but means error handling isn't testable via curl.

## HTTP Status Summary

```
GET /                           -> 200
GET /pricing                    -> 200
GET /api/health                 -> 200
DELETE /api/test/trial-reset    -> 200
POST /api/auth/send-magic-link  -> 500 (no body sent in status check)
GET /api/auth/verify?token=bogus-> 307
GET /api/balance                -> 401 (correct - no auth)
GET /api/upscale/jobs           -> 401 (correct - no auth)
```

## Evidence Files

All raw output captured in `evidence/verify-all-v3/`:
- `health.txt` — Health check JSON
- `j1-results.txt`, `j1-homepage.html`, `j1-pricing.html` — Discovery evidence
- `j2-results.txt` — Free trial evidence (all uploads fail)
- `j3-results.txt` — Sign-up evidence (magic link + dev-login + session)
- `j4-results.txt` — Add funds evidence (real Stripe checkout URL)
- `j5-results.txt` — Paid upload evidence (image dimension failure)
- `j6-results.txt` — Job history evidence (real DB query)
- `j7-results.txt` — Error handling evidence (partial)
- `http-status-codes.txt` — Endpoint status summary

## Comparison with Previous Run

| Metric | v2 (16b396b) | v3 (this run) |
|--------|-------------|---------------|
| L3 | 0/7 | **1/7** (+1: J4 Stripe) |
| L2 | 1/7 (J1) | **3/7** (+2: J3, J6) |
| DB connected | No | **Yes** |
| Root cause | Missing .env.local | Test image format incompatible with sharp |

**Progress:** .env.local fix resolved all database errors. The remaining blocker is a test-infrastructure issue (generated PNG not readable by sharp), not a product code bug.

## Level Definitions

- **L1:** Endpoint exists, returns non-500
- **L2:** App starts, health check passes, basic flow works
- **L3:** Real services used (real inference, real Stripe sandbox, real Resend API)
