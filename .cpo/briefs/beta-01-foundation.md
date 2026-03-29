# Brief — Project Foundation + Database Schema

**Scope:** Scaffold the Next.js application, set up Drizzle ORM with Neon Postgres, and create the complete database schema for Beta.
**Branch:** `feature/foundation` — new worktree
**Effort estimate:** L (~2 hours)
**Risk:** Low
**Affects:** New project scaffold (frontend/), database schema, package.json, tsconfig, Drizzle config
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Node.js >= 20: `node --version`
- [ ] npm >= 10: `npm --version`
- [ ] Python 3.11+: `python3 --version`

### Credentials & Access
- [ ] Neon `DATABASE_URL` connection string available as environment variable or in `.env.local`
- [ ] Verify connection: `npx drizzle-kit push` succeeds

### Verification Capability
- [ ] Can verify via: `npm run build && npm run dev` + `curl localhost:3000/api/health`
- [ ] Can verify schema via: `npx drizzle-kit studio` (opens Drizzle Studio UI)

### Human Dependencies
- [ ] Neon database created and `DATABASE_URL` provided — needed before any database work

---

## 1. The Problem (Why)

There is no application code yet. The project has a validated POC (FastAPI inference service) and a thorough architecture document, but no frontend, no database, and no project scaffold. Everything else depends on this foundation.

---

## 2. The Solution (What)

### 2.1 Next.js App Scaffold

Create a Next.js 15 application with:
- App Router
- TypeScript strict mode
- Tailwind CSS
- ESLint
- Project structure:
  ```
  frontend/
  ├── src/
  │   ├── app/              # App Router pages
  │   │   ├── layout.tsx
  │   │   ├── page.tsx      # Landing (placeholder)
  │   │   ├── pricing/
  │   │   ├── auth/
  │   │   ├── account/
  │   │   └── jobs/
  │   ├── components/       # Shared components
  │   ├── lib/
  │   │   ├── db/           # Drizzle config + schema
  │   │   ├── auth/         # Auth utilities (placeholder)
  │   │   └── stripe/       # Stripe utilities (placeholder)
  │   └── middleware.ts     # Auth middleware (placeholder)
  ├── drizzle.config.ts
  ├── .env.local.example
  └── package.json
  ```

### 2.2 Database Schema (Drizzle ORM)

Implement the full schema from docs/architecture.md with these corrections:

**Critical change: Use microdollars instead of cents.** All monetary fields use microdollars (1 microdollar = $0.000001) as BIGINT type. This resolves the sub-cent pricing issue (compute costs of $0.001-$0.005 cannot be represented in cents). Use BIGINT (not INTEGER) — INTEGER maxes at ~$2,147 in microdollars which is insufficient for aggregate operations.

Tables:
- `users` — id (UUID), email (unique), created_at, updated_at
- `magic_link_tokens` — id, email, token_hash, expires_at, used, created_at
- `balances` — user_id (PK, FK→users), amount_microdollars (CHECK >= 0), updated_at
- `transactions` — id, user_id, type (deposit/charge/refund), amount_microdollars, stripe_payment_intent_id, stripe_checkout_session_id, job_id, description, created_at
- `jobs` — id, user_id, status, input/output dimensions, file sizes, processing_time_ms, compute_cost_microdollars, platform_fee_microdollars (default 5000 = $0.005), total_cost_microdollars, output_gcs_key, error_message, created_at, completed_at
- `free_trial_uses` — id, ip_hash (SHA-256 of IP), uses_count, first_use_at, last_use_at

Indexes as specified in architecture doc, plus:
- `idx_free_trial_ip` on `free_trial_uses(ip_hash)`

### 2.3 API Health Check

- `GET /api/health` — returns `{ "status": "ok", "version": "0.1.0" }`
- Verifies database connectivity

### 2.4 Development Configuration

- `.env.local.example` with all required environment variables documented
- `drizzle.config.ts` using `@neondatabase/serverless` HTTP driver
- npm scripts: `dev`, `build`, `start`, `db:push`, `db:studio`, `db:generate`

---

## 3. Design Alignment

This establishes the technical foundation aligned with ADR-001 (Hybrid architecture), ADR-002 (Neon Postgres), and ADR-003 (REST API). The microdollar unit system resolves the CEO's open question about sub-cent pricing.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Architecture

**Stage-appropriate work in this brief:**
- Schema design (Architecture stage)
- Project scaffold generation (Architecture stage — allowed)

**Out of scope for this stage:**
- Feature code beyond health check
- UI beyond placeholder pages
- Auth/payment integration code

---

## 4. Implementation Plan

### Phase 1: Scaffold
- `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir`
- Install Drizzle ORM: `npm install drizzle-orm @neondatabase/serverless`
- Install dev deps: `npm install -D drizzle-kit`
- Create project structure (directories, placeholder pages)

### Phase 2: Database Schema
- Define schema in `src/lib/db/schema.ts` using Drizzle's TypeScript schema builder
- Create `src/lib/db/index.ts` with Neon HTTP connection
- Create `drizzle.config.ts`
- Run `npx drizzle-kit push` to create tables in Neon

### Phase 3: Health Check + Verify
- Create `src/app/api/health/route.ts`
- Verify: `npm run dev` → `curl localhost:3000/api/health`
- Verify: `npx drizzle-kit studio` shows all tables

---

## 5. Parameters

| Parameter ID | Name | Type | Value | What It Controls |
|-------------|------|------|-------|-----------------|
| MICRODOLLAR_UNIT | Monetary unit | constant | 1 microdollar = $0.000001 | All monetary calculations |
| PLATFORM_FEE | Platform fee per image | constant | 5000 microdollars ($0.005) | Default platform_fee_microdollars |

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| `npm run build` succeeds | TypeScript compiles, no errors |
| `curl localhost:3000/api/health` returns 200 | App serves requests |
| Health check returns DB status | Neon connection works |
| `npx drizzle-kit studio` shows all 6 tables | Schema deployed correctly |
| Balance CHECK constraint test | Negative balance is rejected by DB |

### Acceptance Criteria
- [ ] Next.js app builds and serves on localhost:3000
- [ ] All 6 database tables created in Neon with correct columns and constraints
- [ ] Microdollar unit used for all monetary fields (not cents)
- [ ] Health check endpoint returns 200 with DB status
- [ ] `.env.local.example` documents all required environment variables
- [ ] Build succeeds, no TypeScript errors

---

## 7. What This Does NOT Include

- Authentication implementation (Brief 3)
- Stripe integration (Brief 4)
- Inference service changes (Brief 2)
- Any feature UI beyond placeholder pages
- CI/CD or deployment configuration (Brief 7)
- Seeding test data

---

## 8. Challenge Points

- [ ] **Neon HTTP driver compatibility:** Assume `@neondatabase/serverless` works with Drizzle ORM's latest version. If not, may need `postgres` driver with Neon's connection pooler instead.
- [ ] **Microdollar precision:** Use BIGINT (64-bit) for all microdollar columns. Research confirms INTEGER (32-bit, max ~$2,147) is too small for aggregate operations and reporting even if individual balances are small.
- [ ] **Next.js 15 App Router stability:** Assume App Router is stable for API routes with streaming/long responses. Verify that API route timeouts can be configured for the 47s upscale proxy.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Neon connection fails | Can't verify schema | Test with `psql $DATABASE_URL` first |
| Drizzle ORM version conflict | Schema migration fails | Pin versions, test `db:push` early |
| INTEGER overflow for microdollars | Balance cap too low | Use BIGINT if max balance > $2,147 needed |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/foundation`
2. `gh pr create --title "PRJ-001: Project foundation + database schema" --body "..." --base main --head feature/foundation`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Fully autonomous.** No human interaction needed after Neon DATABASE_URL is provided.

---

*Brief version: 1.0 — 2026-03-29*
