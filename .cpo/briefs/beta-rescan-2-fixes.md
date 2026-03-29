# Supervisor Brief — Rescan Fix: Gmail→Resend Migration + Env Alignment

**Branch:** `fix/resend-migration`
**Executor session:** `exec-rescan2`

## 1. The Problem

Brief 3 implemented magic link auth using Gmail SMTP (nodemailer + EMAIL_FROM + EMAIL_APP_PASSWORD), but the CEO approved Resend as the email provider. The `.env.local` has `RESEND_API_KEY` but the app doesn't use it. Additionally, `GCS_BUCKET_NAME` needs to be added to `.env.local`.

## 2. The Solution

Three targeted fixes:

### Fix A: Migrate email from Gmail to Resend

1. Read `frontend/src/lib/auth/email.ts` — this is the Gmail implementation
2. Replace with Resend SDK implementation:
   - `npm install resend` in the frontend directory
   - Use `RESEND_API_KEY` env var (already set in .env.local)
   - Send from `onboarding@resend.dev` for testing (no custom domain yet)
   - Keep the same interface: `sendMagicLinkEmail(email, token)` function signature
3. Remove `nodemailer` dependency: `npm uninstall nodemailer @types/nodemailer`
4. Remove `EMAIL_FROM` and `EMAIL_APP_PASSWORD` from `.env.local.example`
5. Add `RESEND_API_KEY` to `.env.local.example`
6. Update `src/lib/env-check.ts` to check for `RESEND_API_KEY` instead of `EMAIL_FROM`/`EMAIL_APP_PASSWORD`

### Fix B: Add GCS_BUCKET_NAME to frontend .env.local

The frontend `.env.local` is missing `GCS_BUCKET_NAME`. Add it:
```
GCS_BUCKET_NAME=honest-image-tools-results
```

### Fix C: Sync .env.local.example with reality

Update `.env.local.example` to match what the app ACTUALLY needs:
- `DATABASE_URL` — yes
- `STRIPE_SECRET_KEY` — yes
- `STRIPE_PUBLISHABLE_KEY` — yes (even if only for future client-side use)
- `STRIPE_WEBHOOK_SECRET` — yes
- `RESEND_API_KEY` — yes (replacing EMAIL_FROM + EMAIL_APP_PASSWORD)
- `GCS_BUCKET_NAME` — yes
- `JWT_SECRET` — yes
- `INFERENCE_SERVICE_URL` — optional
- `NEXT_PUBLIC_BASE_URL` or `NEXT_PUBLIC_APP_URL` — reconcile which one the app uses
- Remove `EMAIL_FROM`, `EMAIL_APP_PASSWORD` (no longer used)

## 3. Verification

```bash
# 1. Build passes
cd frontend && npm run build

# 2. Resend import works (no nodemailer)
grep -r "nodemailer" frontend/src/ # should return nothing
grep -r "resend" frontend/src/lib/auth/ # should find the Resend import

# 3. Env check passes
# Start dev server and check it doesn't warn about missing EMAIL_FROM

# 4. Test magic link send (if RESEND_API_KEY is real)
# curl -X POST http://localhost:3001/api/auth/send-magic-link -H "Content-Type: application/json" -d '{"email":"YOUR_EMAIL"}'
```

## 4. What This Does NOT Include

- Do NOT change any other auth logic (JWT, sessions, rate limiting)
- Do NOT add custom domain to Resend (that's Production stage)
- Do NOT touch Stripe, GCS, or inference code

---

## 6. Lifecycle Stage & Scope Lock

**Current lifecycle stage:** Beta (gate BLOCKED — rescan fixes)
**Scope lock:** Fix email provider + env alignment only. No new features.

---

**When complete:** Push branch, create PR, self-terminate.
