# Brief — Authentication System (Magic Links)

**Scope:** Implement email magic link authentication with Gmail SMTP, JWT sessions, and rate limiting.
**Branch:** `feature/auth` — new worktree
**Effort estimate:** L (~2 hours)
**Risk:** Medium (email deliverability is a risk)
**Affects:** `frontend/src/app/api/auth/`, `frontend/src/lib/auth/`, `frontend/src/app/auth/`, `frontend/src/middleware.ts`
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Node.js >= 20: `node --version`
- [ ] Brief 1 (Foundation) completed: `frontend/` directory exists with Drizzle schema

### Credentials & Access
- [ ] Neon `DATABASE_URL` available in `.env.local`
- [ ] Gmail App Password available: Google Account → Security → 2-Step Verification → App Passwords → generate for "Mail"
- [ ] Store as `EMAIL_FROM` (the Gmail address) and `EMAIL_APP_PASSWORD` in `.env.local`
- [ ] `JWT_SECRET` (256-bit random hex): `openssl rand -hex 32`

### Verification Capability
- [ ] Can verify via: `npm run dev` → test magic link flow manually
- [ ] Can verify email sending: send test email to own address
- [ ] Can verify JWT: decode token at jwt.io (dev only)

### Human Dependencies
- [ ] Gmail App Password generated — needed before email sending works
- [ ] JWT_SECRET generated — agent can do this

---

## 1. The Problem (Why)

Users need accounts to hold balances and track transaction history. The architecture specifies passwordless magic link authentication — simple, secure, no password management overhead. The CEO decided email sending should use a Google account (Gmail SMTP), not Resend or SendGrid.

---

## 2. The Solution (What)

### 2.1 Magic Link Request

**POST /api/auth/send-magic-link**
1. Receive `{ email }` in request body
2. Rate-limit: max 3 magic link requests per email per hour (use `magic_link_tokens` table, count recent entries)
3. Generate 32-byte random token → hex encode
4. Hash token with SHA-256
5. Store `{ email, token_hash, expires_at: now + 15min, used: false }` in `magic_link_tokens`
6. Send email via Gmail SMTP (Nodemailer) with link: `{BASE_URL}/auth/verify?token={token}`
7. Return `{ message: "Magic link sent. Check your email." }`

Email template: simple, plain HTML with the magic link button. Subject: "Sign in to Honest Image Tools". No fancy template — keep it fast and deliverable.

### 2.2 Magic Link Verification

**GET /auth/verify?token={token}** (this is a page route, not an API route)
1. Hash the received token with SHA-256
2. Query `magic_link_tokens` for matching `token_hash` where `used = false` and `expires_at > now()`
3. If not found: render error page "Invalid or expired link"
4. Mark token as `used = true`
5. Find or create user by email in `users` table
6. Ensure `balances` row exists (create with `amount_microdollars = 0` if new user)
7. Create signed JWT: `{ userId, email, iat, exp: now + 30 days }`
8. Set HTTP-only cookie: `session={jwt}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000`
9. Redirect to `/account`

### 2.3 Session Management

**JWT Configuration:**
- Algorithm: HS256
- Secret: `JWT_SECRET` environment variable
- Payload: `{ sub: userId, email, iat, exp }`
- Expiry: 30 days
- Cookie: `session`, HTTP-only, Secure, SameSite=Lax

**Middleware** (`middleware.ts`):
- Check for `session` cookie on protected routes (`/api/balance/*`, `/api/upscale/*`, `/account/*`)
- Verify JWT signature and expiry
- Inject `userId` and `email` into request context (via headers or Next.js `cookies()`)
- Return 401 for invalid/missing session on API routes
- Redirect to `/auth/login` for invalid session on page routes

### 2.4 Logout

**POST /api/auth/logout**
1. Clear the `session` cookie (set empty value, Max-Age=0)
2. Return `{ message: "Logged out." }`

### 2.5 Gmail SMTP Setup

Use Nodemailer with Gmail:
```
npm install nodemailer
npm install -D @types/nodemailer
```

Transport config:
```typescript
{
  host: "smtp.gmail.com",
  port: 587,
  secure: false,  // STARTTLS
  auth: {
    user: process.env.EMAIL_FROM,
    pass: process.env.EMAIL_APP_PASSWORD,
  },
}
```

### 2.6 Auth Utility Functions

Create `src/lib/auth/`:
- `jwt.ts` — sign/verify JWT, get session from cookies
- `email.ts` — send magic link email via Nodemailer
- `tokens.ts` — generate token, hash token, store/verify in DB
- `middleware.ts` — auth check helper for API routes

---

## 3. Design Alignment

Implements ADR-007 (Magic Link Auth) with the CEO's modification: Gmail SMTP instead of Resend/SendGrid. Aligns with the "no dark patterns" principle — simple auth, no password complexity.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Architecture → Beta transition

**Stage-appropriate work in this brief:**
- Auth system is a Beta pillar (see lifecycle.md)
- Needed before any user-facing feature

**Out of scope for this stage:**
- OAuth providers (Google/GitHub login)
- Two-factor authentication
- Account deletion flow
- Admin roles or permissions

---

## 4. Implementation Plan

### Phase 1: JWT + Session Utilities
- Create `src/lib/auth/jwt.ts` with sign/verify functions using `jose` library
- Create `src/middleware.ts` with route protection
- Test: protected route returns 401 without cookie

### Phase 2: Magic Link Flow
- Create `src/lib/auth/tokens.ts` — token generation, hashing, DB operations
- Create `src/lib/auth/email.ts` — Nodemailer transport, send magic link
- Create API route: `POST /api/auth/send-magic-link`
- Create page route: `/auth/verify` — token verification, user creation, cookie setting
- Test: full magic link flow end-to-end

### Phase 3: Login/Logout UI
- Create `/auth/login` page — email input form
- Create `POST /api/auth/logout` — clear cookie
- Create basic auth state display (logged in email, logout button)

### Phase 4: Rate Limiting
- Implement per-email rate limit (3/hour) in magic link endpoint
- Test: 4th request within an hour returns 429

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| POST /api/auth/send-magic-link with valid email → 200 + email sent | Magic link flow works |
| POST /api/auth/send-magic-link 4x same email → 429 | Rate limiting works |
| GET /auth/verify?token=valid → redirect to /account with session cookie | Token verification works |
| GET /auth/verify?token=invalid → error page | Invalid tokens rejected |
| GET /auth/verify?token=used → error page | Replay protection works |
| GET /auth/verify?token=expired → error page | Expiry enforced |
| GET /api/balance without cookie → 401 | Middleware blocks unauthenticated |
| GET /api/balance with valid cookie → 200 | Middleware passes authenticated |
| POST /api/auth/logout → cookie cleared | Logout works |

### Acceptance Criteria
- [ ] Magic link email is received within 30 seconds
- [ ] Clicking the link logs the user in and redirects to /account
- [ ] Session persists across browser restarts (30-day cookie)
- [ ] Protected routes return 401 without valid session
- [ ] Rate limiting prevents > 3 magic links per email per hour
- [ ] Tokens are single-use (replay returns error)
- [ ] Tokens expire after 15 minutes
- [ ] JWT cookie is HTTP-only, Secure, SameSite=Lax
- [ ] New users get a balance record with 0 microdollars

---

## 7. What This Does NOT Include

- Password-based authentication
- Social login (OAuth)
- Account settings/profile editing
- Email verification (magic link IS verification)
- CSRF token system (SameSite=Lax cookie handles this)
- Admin authentication

---

## 8. Challenge Points

- [ ] **Gmail deliverability:** Assume magic link emails from Gmail don't land in spam. Test by sending to the developer's own email. If spam issues arise, add SPF/DKIM records or switch to a transactional email provider (architecture change is minimal — only the transport layer in `email.ts` changes).
- [ ] **Gmail rate limits:** Assume 500 emails/day (regular Gmail) is sufficient for Beta. If using Google Workspace, limit is 2,000/day. Verify which account type is being used.
- [ ] **jose vs jsonwebtoken:** Assume `jose` library works well in Next.js Edge Runtime. If middleware runs in Edge, `jsonwebtoken` (which uses Node.js `crypto`) won't work — `jose` is the Web Crypto API alternative.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Gmail marks our emails as spam | Users can't log in | Test immediately; add SPF record; fallback to Resend ($0) |
| App Password gets revoked | Email sending breaks | Monitor for sending failures; alert on first failure |
| JWT secret leaked | All sessions compromised | Rotate secret, invalidate all sessions |
| Edge Runtime incompatibility | Middleware breaks | Use `jose` not `jsonwebtoken`; test in Edge |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/auth`
2. `gh pr create --title "PRJ-001: Magic link auth + JWT sessions" --body "..." --base main --head feature/auth`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Mostly autonomous.** Requires Gmail App Password from human before email sending can be tested. All other work is autonomous.

---

*Brief version: 1.0 — 2026-03-29*
