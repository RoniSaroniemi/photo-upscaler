# Honest Image Tools — Architecture Document

*Stage: Architecture | Date: 2026-03-29 | Based on POC findings from PR #5 and #6*

---

## System Diagram

```
                          +---------------------------+
                          |       User Browser        |
                          +---------------------------+
                                     |
                                     | HTTPS
                                     v
                          +---------------------------+
                          |   Next.js on Cloud Run    |
                          |   (frontend + API routes) |
                          |                           |
                          |  /api/auth/*              |
                          |  /api/balance/*           |
                          |  /api/upscale/*           |
                          |  /api/pricing/*           |
                          +---------------------------+
                            |       |          |
                +-----------+       |          +------------+
                |                   |                       |
                v                   v                       v
    +----------------+  +-------------------+   +-------------------+
    |   Neon Postgres    |  |  Inference Cloud  |   |      Stripe       |
    |   (Postgres)   |  |  Run Service      |   |   (payments)      |
    |                |  |                   |   |                   |
    |  users         |  |  POST /upscale    |   |  Checkout Session |
    |  balances      |  |  GET  /health     |   |  Webhooks         |
    |  transactions  |  |  GET  /estimate   |   +-------------------+
    |  jobs          |  |                   |
    +----------------+  |  FastAPI +        |
                        |  Real-ESRGAN      |
                        |  (4 vCPU, 8 GiB)  |
                        +-------------------+
                                 |
                                 v
                        +-------------------+
                        |  GCS Bucket       |
                        |  (temp storage)   |
                        |  24h lifecycle    |
                        +-------------------+
```

**Data flow for an upscale request:**

```
1. User selects image in browser
2. Browser reads dimensions, calls GET /api/pricing/estimate?w=1024&h=768
3. UI shows estimated cost; user confirms
4. Browser uploads image to POST /api/upscale
5. Next.js API route:
   a. Checks user balance >= estimated cost
   b. Creates job record (status: pending)
   c. Forwards image to inference service
   d. Inference returns upscaled image + X-Processing-Time-Ms header
   e. Calculates actual cost from processing time
   f. Uploads result to GCS with 24h expiry
   g. Deducts actual cost from balance
   h. Creates transaction record
   i. Updates job (status: complete, cost breakdown, signed URL)
6. Browser polls GET /api/upscale/jobs/:id for status
7. User downloads via signed GCS URL
```

---

## ADR-001: Service Structure

### Context

We need to decide how to structure the application. The frontend (Next.js) and inference engine (Python + Real-ESRGAN) use different runtimes. The inference service is CPU-intensive (10-47s per image) while the frontend handles lightweight HTTP requests.

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **(A) Monolith** | Next.js + Python in one container | Simplest deployment | Can't scale independently; Node.js + Python in one container is awkward; inference blocks the container |
| **(B) Split** | Separate Next.js and FastAPI Cloud Run services | Independent scaling; clean separation; inference can scale to zero separately | Two services to manage; network hop between them |
| **(C) Hybrid** | Next.js API routes proxy to Python inference service | Frontend has full control; inference is isolated; API routes handle auth/billing logic | Still two services; proxy adds slight latency |

### Decision

**Option C: Hybrid** -- Next.js frontend with API routes that proxy to a separate Python inference Cloud Run service.

### Rationale

1. **Independent scaling is essential.** The frontend handles auth, payments, and page rendering (fast, cheap). The inference service processes images (slow, expensive, CPU-bound). They have completely different scaling profiles. The inference service should scale to zero when idle; the frontend should stay warm for instant page loads.

2. **API routes own business logic.** Auth checks, balance verification, cost calculation, transaction recording -- all happen in the Next.js API routes. The inference service is a dumb pipe: image in, upscaled image out. This keeps the Python service simple and focused.

3. **Clean upgrade path to GPU.** When we add GPU support for 1920px+ images, we deploy a second inference service (GPU-backed) alongside the CPU one. The API route decides which to call based on image dimensions. No frontend changes needed.

4. **Developer experience.** Next.js developers work in TypeScript. ML/inference work stays in Python. No cross-language container builds.

5. **Cost.** Inference Cloud Run scales to zero ($0 when idle). Frontend Cloud Run can use minimum 1 instance for fast page loads ($5-10/month) or also scale to zero for maximum savings.

### Consequences

- Two Cloud Run services to deploy and monitor.
- Internal service-to-service auth needed (Cloud Run IAM or shared secret).
- Network hop adds ~50-100ms per request (negligible vs 10-47s processing).

---

## ADR-002: Database

### Context

We need persistent storage for users, balances, transactions, and job records. Cloud Run containers are ephemeral -- no local disk persistence. The database must be accessible from Cloud Run, handle concurrent writes safely (especially balance updates), and be cost-effective for a small-scale launch.

### Options Considered

| Option | Pros | Cons |
|--------|------|------|
| **Neon Postgres (Postgres)** | Full SQL, ACID transactions, managed, connection pooling via pgBouncer or Neon Postgres Auth Proxy | $7-10/month minimum (db-f1-micro); connection management on serverless |
| **Firestore** | Serverless, scales to zero, no connection pooling needed, GCP-native | NoSQL -- harder for financial data requiring ACID; query limitations; vendor lock-in |
| **Neon (serverless Postgres)** | True serverless Postgres, HTTP-based driver (no connection pooling issue), generous free tier | Third-party dependency; less GCP integration |
| **SQLite on Cloud Storage** | $0 cost, simple | No concurrent writes; unsuitable for production |

### Decision

**Neon (serverless Postgres)** for MVP/Beta. Migrate to Neon Postgres Postgres if scale demands it.

### Rationale

1. **ACID transactions are non-negotiable.** We are handling real money (USD balances). "Deduct balance, record transaction, update job" must be atomic. Postgres provides this natively. Firestore's transactions are more limited and harder to reason about for financial operations.

2. **Serverless solves connection pooling.** Cloud Run's ephemeral containers create and destroy database connections unpredictably. Neon Postgres requires careful connection pooling (pgBouncer, Neon Postgres Proxy). Neon's HTTP-based driver (`@neondatabase/serverless`) works natively with serverless -- each request opens and closes a connection with near-zero overhead.

3. **Cost at MVP scale.** Neon's free tier provides 0.5 GiB storage and 190 hours of compute/month -- more than enough for beta. Neon Postgres's minimum is ~$7-10/month even idle. For a project optimizing for cost transparency, the database should also be cost-efficient.

4. **Migration is easy.** Both Neon and Neon Postgres are Postgres. If we outgrow Neon, `pg_dump` and `pg_restore` is a one-command migration. Schema, queries, and ORM code remain identical.

5. **Drizzle ORM.** We'll use Drizzle ORM (TypeScript) for type-safe schema definitions and queries. It supports both Neon's HTTP driver and standard Postgres drivers, making the migration path seamless.

### Consequences

- Third-party dependency (Neon) instead of fully GCP-native.
- Free tier has compute-hour limits -- monitor usage.
- Must design schema to avoid long-running transactions (keep them fast).

---

## ADR-003: API Design

### Context

The Next.js API routes form the public-facing API. The inference service has a private internal API. We need clear contracts for both.

### Decision

RESTful API with JSON request/response bodies. No GraphQL (overkill for this scope). Authentication via HTTP-only cookies containing a session token.

See the full API contract in the "API Contract" section below.

### Rationale

- REST is simple, well-understood, and sufficient for our use case.
- HTTP-only cookies for session management: secure against XSS, simple to implement with Next.js middleware.
- The inference service API stays minimal (one endpoint) because all business logic lives in the Next.js layer.

---

## ADR-004: Cost Display and Platform Fee

### Context

Our key differentiator is showing the cost breakdown on every image. We need to decide: (1) how to calculate compute cost, (2) what the platform fee is, and (3) how to display it.

### Options for Platform Fee

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **Flat fee per image** | e.g., $0.005 per image | Simple, predictable | Feels unfair on tiny images |
| **Percentage markup** | e.g., 100% markup on compute | Scales with image size | Percentage may seem high even though absolute is tiny |
| **Tiered** | Different fees for different sizes | Flexible | Complex for users to understand |

### Decision

**Flat $0.005 platform fee per image** for MVP. Revisit if compute costs change significantly with GPU.

### Rationale

1. **Radical simplicity.** The whole product pitch is "no hidden costs." A flat fee is the simplest thing to explain: "You pay what it costs us to process your image, plus $0.005 to keep the lights on."

2. **Honest at every price point.** For a 640px image: $0.001 compute + $0.005 platform = $0.006 total. The platform fee is larger than compute, and we show that openly. This is the opposite of what competitors do (hide the markup). Users who see this will trust us.

3. **Revenue math works.** At $0.005/image, 1000 images/day = $5/day = $150/month in platform fees. Not getting rich, but covers infrastructure with room to grow. The key is volume, not per-image margin.

4. **Revisit for GPU tier.** When we add GPU support (1920px+), compute cost jumps to ~$0.02-0.05. The $0.005 flat fee still works there -- it becomes a smaller fraction of total cost.

### Cost Display Design

Every completed job shows:

```
Cost Breakdown
  Compute:      $0.003    (26.0s processing)
  Platform fee: $0.005
  ─────────────────────
  Total:        $0.008    deducted from balance
```

Pre-upload estimate shows:

```
Estimated cost: ~$0.008
  Based on: 1024x768 image, ~26s processing
  Compute: ~$0.003 | Platform: $0.005
```

### Consequences

- Platform fee is visible and may seem high relative to compute for small images. This is intentional -- honesty over optics.
- Need to clearly communicate the fee structure on the pricing page.

---

## ADR-005: Image Handling

### Context

Users upload images (up to 1024px for MVP), receive 4x upscaled results. Output PNGs from the POC are 12-25 MB -- too large for practical use. We need decisions on: input constraints, output format, temporary storage, and download delivery.

### Decision

- **Input:** Max 1024px on longest side (MVP). Accept JPEG, PNG, WebP. Validate dimensions client-side and server-side. Images larger than 1024px are resized down before upscaling (with user confirmation).
- **Output:** WebP at quality 90 as default. Optional JPEG download. No PNG (too large).
- **Storage:** Google Cloud Storage bucket with 24-hour lifecycle deletion policy. Images stored with random UUID keys (no user-identifiable naming).
- **Download:** Signed URLs with 1-hour expiry. Generated after job completion, included in job status response.

### Rationale

1. **WebP output.** A 4096x3072 WebP at quality 90 is ~1-3 MB vs 12-25 MB PNG. Dramatically better user experience for download and storage. All modern browsers support WebP. Users who need PNG can convert locally.

2. **1024px limit.** POC proved 1920px+ fails on CPU (OOM). Rather than a broken experience, we hard-cap at 1024px for MVP. The UI explains why and mentions GPU support coming later.

3. **GCS with lifecycle.** "Delete by default" is a core principle. GCS lifecycle policies automatically delete objects after 24 hours. No cron jobs, no manual cleanup. Cost is negligible (~$0.001/GB/month).

4. **Signed URLs.** No auth needed to download -- the URL itself is the credential, and it expires in 1 hour. Simple for users (direct download link), secure (can't guess URLs, they expire fast).

5. **No input storage.** Input images are streamed to the inference service and discarded. Only the output is stored temporarily. This minimizes data retention.

### Consequences

- Users have 1 hour to download (and can re-trigger from their job history within 24 hours).
- After 24 hours, the result is gone permanently. The job record remains (for billing history) but the image is deleted.
- Must convert inference output from PNG to WebP in the API route before storing.

---

## ADR-006: Frontend Architecture

### Context

The frontend is a Next.js application serving the upload flow, account management, and pricing information. Key challenge: image processing takes 10-47 seconds, requiring real-time progress feedback.

### Decision

- **Next.js App Router** with server components for static/data-fetching pages, client components for interactive upload flow.
- **Polling** for job status (not WebSockets).
- **Tailwind CSS** for styling. No component library -- the UI is simple enough.
- **Mobile-first responsive design.**

### Rationale

1. **App Router.** Next.js App Router is the current standard. Server components handle the pricing page, account page, and balance display efficiently (data fetched on the server, no client JS needed). The upload flow is a client component (needs file input, progress, interactivity).

2. **Polling over WebSockets.** Processing takes 10-47 seconds. A simple `setInterval` polling every 2 seconds (GET /api/upscale/jobs/:id) is far simpler than WebSocket infrastructure. At 2s intervals, a 47s job makes ~24 requests -- trivial load. WebSockets add complexity (connection management, reconnection, Cloud Run timeout considerations) for no real benefit at our scale.

3. **Progress UX.** We cannot get real progress from Real-ESRGAN (it processes tiles internally). Instead:
   - Show estimated time based on image dimensions (from the pricing formula).
   - Show an animated progress bar that reaches ~90% at the estimated time, then waits.
   - Show "Processing..." with elapsed time counter.
   - When complete, show the cost breakdown and download link.

4. **Tailwind.** Fast to build, no runtime CSS overhead, good for a small team. The UI has ~5 pages -- a component library would be overkill.

### Page Structure

```
/                     Landing page + upload (server + client components)
/pricing              Pricing explanation + calculator (server component)
/auth/login           Magic link request (client component)
/auth/verify          Magic link verification (server component)
/account              Balance, transaction history (server component)
/account/add-funds    Stripe checkout flow (client component)
/jobs/:id             Job status + result (client component for polling)
```

### Consequences

- No real-time progress (only estimated progress bar). Acceptable for MVP.
- Polling creates some unnecessary requests but is operationally simple.
- Must handle the case where user closes browser mid-processing (job completes, balance is deducted, result waits in GCS for download later).

---

## ADR-007: Authentication

### Context

The product needs user accounts for balance management and transaction history. The requirement is email magic link -- no passwords.

### Decision

**Custom magic link implementation** using the database and Next.js API routes. No third-party auth provider.

### Flow

```
1. User enters email at /auth/login
2. POST /api/auth/send-magic-link
   - Generate random token (32 bytes, hex-encoded)
   - Store: { email, token_hash, expires_at: now+15min, used: false }
   - Send email with link: /auth/verify?token=<token>
3. User clicks link in email
4. GET /auth/verify?token=<token>
   - Server verifies token (hash match, not expired, not used)
   - Mark token as used
   - Find or create user by email
   - Set HTTP-only session cookie (signed JWT, 30-day expiry)
   - Redirect to / or /account
5. Subsequent requests include cookie automatically
6. API routes verify cookie via middleware
```

### Rationale

1. **No auth provider needed.** Firebase Auth, Auth0, Clerk -- all add cost, complexity, and vendor lock-in. A magic link system is ~100 lines of code. We store a hashed token, verify it, set a cookie. Done.

2. **Email delivery.** Use Resend (or SendGrid) for transactional email. ~$0 at our scale (free tier handles thousands/month).

3. **Session management.** Signed JWT in an HTTP-only cookie. Contains: `{ userId, email, iat, exp }`. No session table needed (stateless). 30-day expiry -- users who upscale occasionally shouldn't need to re-auth constantly.

4. **No passwords means no password problems.** No hashing, no reset flows, no breaches of password databases. The email IS the authentication factor.

### Consequences

- Users must have access to their email to log in (every time, unless session cookie is still valid).
- Magic link tokens are single-use and expire in 15 minutes.
- Must rate-limit magic link requests to prevent email abuse (max 3 per email per hour).

---

## ADR-008: Free Trial

### Decision

1-2 free upscales per IP address, no auth required.

### Implementation

- Track via `free_trial_uses` table with SHA-256 hashed IP (never store raw IPs).
- Check: `SELECT COUNT(*) FROM free_trial_uses WHERE ip_hash = $hash` < 2.
- Free trial skips auth and balance check. Job is created without a user_id (nullable).
- No cost displayed for free images — instead show: "This upscale would normally cost $X."
- After free trial exhausted, prompt to create account and add funds.

### Rationale

CEO directive: emphasize honest pricing over free samples. The free trial demonstrates quality and transparency — users see what it *would* cost, building trust before they deposit.

---

## ADR-009: Error Handling

### Decision

No-charge guarantee: if processing fails for any reason, the user is never charged.

### Implementation

- **Inference failure:** API route catches non-200 from inference service. Job marked `failed`, no balance deduction, no transaction created.
- **GCS upload failure:** Inference succeeded but storage failed. Retry once. If still fails, job marked `failed`, refund transaction created if balance was already deducted.
- **Stripe webhook failure:** Idempotent handling. Stripe retries for up to 72 hours. Handler checks `stripe_checkout_session_id` uniqueness before crediting.
- **DB failure:** If transaction commit fails mid-charge, Postgres ACID guarantees rollback. Balance unchanged.

### User-Facing Messages

- Processing failed: "Something went wrong. You have not been charged. Please try again."
- Balance issues: "Insufficient balance. Add funds to continue." (with exact amount needed)

---

## ADR-010: Deployment + CI/CD

### Decision

Cloud Build triggers, two Cloud Run services, Cloud Run IAM for service-to-service auth.

### Implementation

- **Frontend service:** Cloud Run, 1 vCPU, 512 MiB, min-instances 0, max 5.
- **Inference service:** Cloud Run, 4 vCPU, 8 GiB, concurrency 1, min 0, max 3.
- **Service-to-service auth:** Frontend has IAM role `roles/run.invoker` on inference service. No shared secrets.
- **CI/CD:** Cloud Build triggers on push to `main`. Separate builds for frontend and inference.
- **Staging:** Deploy to `-staging` suffixed services before production.
- **Secrets:** Cloud Secret Manager for DB URL, Stripe keys, JWT secret, email credentials.

---

## API Contract

### Public API (Next.js API Routes)

All endpoints return JSON. Auth-required endpoints return 401 if no valid session cookie.

---

#### Auth

**POST /api/auth/send-magic-link**

Send a magic link to the user's email.

```
Request:
{
  "email": "user@example.com"
}

Response (200):
{
  "message": "Magic link sent. Check your email."
}

Response (429):
{
  "error": "Too many requests. Try again in X minutes."
}
```

**GET /api/auth/verify?token=\<token\>**

Verify a magic link token. Sets session cookie and redirects.

```
Response (302): Redirect to /account (sets Set-Cookie header)
Response (400): { "error": "Invalid or expired token." }
```

**POST /api/auth/logout**

Clear session cookie.

```
Response (200): { "message": "Logged out." }
```

---

#### Balance

**GET /api/balance** *(auth required)*

Get current balance.

```
Response (200):
{
  "balance_microdollars": 500,
  "currency": "USD",
  "formatted": "$5.00"
}
```

**POST /api/balance/add-funds** *(auth required)*

Create a Stripe Checkout Session to add funds.

```
Request:
{
  "amount_microdollars": 500
}

Response (200):
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_xxx",
  "session_id": "cs_xxx"
}
```

Minimum deposit: $5.00 (5,000,000 microdollars). Preset options in UI: $5, $10, $25.

**POST /api/balance/webhook** *(Stripe webhook, no auth)*

Stripe webhook handler for checkout.session.completed events. Credits the user's balance.

```
Request: Stripe webhook payload (verified via signature)
Response (200): { "received": true }
```

**GET /api/balance/transactions** *(auth required)*

Get transaction history.

```
Request query params:
  ?limit=20&offset=0

Response (200):
{
  "transactions": [
    {
      "id": "txn_abc123",
      "type": "deposit",
      "amount_microdollars": 500,
      "description": "Added funds via Stripe",
      "created_at": "2026-03-29T10:00:00Z"
    },
    {
      "id": "txn_def456",
      "type": "charge",
      "amount_microdollars": -8,
      "description": "Upscale: 1024x768 → 4096x3072",
      "job_id": "job_xyz789",
      "cost_breakdown": {
        "compute_microdollars": 3,
        "platform_fee_microdollars": 5,
        "total_microdollars": 8
      },
      "created_at": "2026-03-29T10:05:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

#### Pricing

**GET /api/pricing/estimate**

Estimate cost for given image dimensions. No auth required (used pre-upload).

```
Request query params:
  ?width=1024&height=768

Response (200):
{
  "input_pixels": 786432,
  "estimated_processing_seconds": 22.0,
  "cost_breakdown": {
    "compute_microdollars": 3,
    "platform_fee_microdollars": 5,
    "total_microdollars": 8
  },
  "formatted_total": "$0.008",
  "max_input_px": 1024,
  "note": "Estimate based on ~28us per input pixel."
}
```

Response if image too large:

```
Response (400):
{
  "error": "Image exceeds maximum dimension of 1024px.",
  "max_input_px": 1024,
  "suggestion": "Resize to 1024px on the longest side before uploading."
}
```

**GET /api/pricing/formula**

Get the current pricing formula (for the pricing page).

```
Response (200):
{
  "compute_rate_per_second": 0.000116,
  "pixel_rate_microseconds": 28,
  "platform_fee_microdollars": 5,
  "currency": "USD",
  "examples": [
    { "input": "640x480", "estimated_total_microdollars": 6 },
    { "input": "1024x768", "estimated_total_microdollars": 8 },
    { "input": "1024x1024", "estimated_total_microdollars": 9 }
  ]
}
```

---

#### Upscale

**POST /api/upscale** *(auth required)*

Upload an image for upscaling.

```
Request: multipart/form-data
  file: <image file>

Response (201):
{
  "job_id": "job_xyz789",
  "status": "pending",
  "estimated_cost": {
    "compute_microdollars": 3,
    "platform_fee_microdollars": 5,
    "total_microdollars": 8
  },
  "estimated_seconds": 22.0
}

Response (400): { "error": "Image exceeds 1024px limit." }
Response (402): { "error": "Insufficient balance.", "required_microdollars": 8, "balance_microdollars": 3 }
Response (413): { "error": "File too large. Maximum 10 MB." }
```

**GET /api/upscale/jobs/:id** *(auth required)*

Get job status and result.

```
Response (200) — processing:
{
  "job_id": "job_xyz789",
  "status": "processing",
  "started_at": "2026-03-29T10:05:00Z",
  "estimated_seconds": 22.0,
  "elapsed_seconds": 8.3
}

Response (200) — complete:
{
  "job_id": "job_xyz789",
  "status": "complete",
  "input_size": "1024x768",
  "output_size": "4096x3072",
  "processing_time_ms": 26012,
  "cost_breakdown": {
    "compute_microdollars": 3,
    "platform_fee_microdollars": 5,
    "total_microdollars": 8
  },
  "download_url": "https://storage.googleapis.com/...",
  "download_expires_at": "2026-03-29T11:05:00Z",
  "created_at": "2026-03-29T10:05:00Z",
  "completed_at": "2026-03-29T10:05:26Z"
}

Response (200) — failed:
{
  "job_id": "job_xyz789",
  "status": "failed",
  "error": "Processing failed. No charge applied.",
  "created_at": "2026-03-29T10:05:00Z"
}
```

**GET /api/upscale/jobs** *(auth required)*

List recent jobs.

```
Request query params:
  ?limit=10&offset=0

Response (200):
{
  "jobs": [ ... ],  // Same shape as single job response
  "total": 15,
  "limit": 10,
  "offset": 0
}
```

---

### Internal API (Inference Service)

Called only by the Next.js API routes. Not publicly accessible.

**POST /upscale**

```
Request: multipart/form-data
  file: <image file>
  scale: 4 (query param, optional, default 4)

Response (200):
  Body: image/webp binary
  Headers:
    X-Processing-Time-Ms: 26012.3
    X-Input-Size: 1024x768
    X-Output-Size: 4096x3072
```

**GET /health**

```
Response (200): { "status": "ok" }
```

**GET /estimate**

```
Request query params:
  ?width=1024&height=768

Response (200):
{
  "pixels": 786432,
  "estimated_seconds": 22.0,
  "estimated_cost_usd": 0.00255
}
```

---

## Data Model

### Schema (Postgres via Drizzle ORM)

```sql
-- Users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users(email);

-- Magic Link Tokens
CREATE TABLE magic_link_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL,
    token_hash      TEXT NOT NULL,          -- SHA-256 hash of the token
    expires_at      TIMESTAMPTZ NOT NULL,
    used            BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_magic_link_tokens_hash ON magic_link_tokens(token_hash);
CREATE INDEX idx_magic_link_tokens_email ON magic_link_tokens(email);

-- Balances (one row per user, updated atomically)
CREATE TABLE balances (
    user_id         UUID PRIMARY KEY REFERENCES users(id),
    amount_microdollars    BIGINT NOT NULL DEFAULT 0,  -- microdollars ($0.000001 units), never negative
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT balance_non_negative CHECK (amount_microdollars >= 0)
    -- 1 microdollar = $0.000001. $5.00 = 5,000,000 microdollars.
);

-- Transactions (append-only ledger)
CREATE TABLE transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id),
    type                    TEXT NOT NULL CHECK (type IN ('deposit', 'charge', 'refund')),
    amount_microdollars            BIGINT NOT NULL,            -- microdollars; positive for deposits, negative for charges
    stripe_payment_intent_id TEXT,                      -- NULL for charges
    stripe_checkout_session_id TEXT,                    -- NULL for charges
    job_id                  UUID,                       -- NULL for deposits
    description             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_transactions_user ON transactions(user_id, created_at DESC);
CREATE INDEX idx_transactions_stripe ON transactions(stripe_checkout_session_id);

-- Jobs
CREATE TABLE jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'complete', 'failed')),
    input_width         INTEGER,
    input_height        INTEGER,
    output_width        INTEGER,
    output_height       INTEGER,
    input_file_size     INTEGER,                    -- bytes
    output_file_size    INTEGER,                    -- bytes
    processing_time_ms  INTEGER,
    compute_cost_microdollars  INTEGER,
    platform_fee_microdollars  INTEGER DEFAULT 5,          -- $0.005 flat fee
    total_cost_microdollars    INTEGER,
    output_gcs_key      TEXT,                       -- GCS object key for result
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_status ON jobs(status) WHERE status IN ('pending', 'processing');

-- Free Trial Tracking
CREATE TABLE free_trial_uses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_hash         TEXT NOT NULL,              -- SHA-256 of IP address (not raw IP)
    job_id          UUID NOT NULL REFERENCES jobs(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_free_trial_ip ON free_trial_uses(ip_hash);
```

### Key Design Decisions

1. **Balance as a separate table with CHECK constraint.** `amount_microdollars >= 0` is enforced at the database level. Even if application code has a bug, the balance can never go negative. This is a financial safety net.

2. **Transactions are append-only.** Never update or delete a transaction. Refunds are new rows with `type: 'refund'` and positive `amount_microdollars`. This creates an auditable ledger.

3. **Amounts in cents (integers).** No floating-point money. Ever. $5.00 = 500 cents. All calculations use integer arithmetic.

4. **Atomic charge operation.** Deducting balance and inserting transaction happen in a single SQL transaction:

```sql
BEGIN;
  UPDATE balances
  SET amount_microdollars = amount_microdollars - $cost,
      updated_at = now()
  WHERE user_id = $user_id
    AND amount_microdollars >= $cost;    -- This fails if insufficient balance

  -- If no row was updated, ROLLBACK (insufficient balance)

  INSERT INTO transactions (user_id, type, amount_microdollars, job_id, description)
  VALUES ($user_id, 'charge', -$cost, $job_id, $description);
COMMIT;
```

5. **Jobs reference transactions via `job_id`.** A completed job always has a matching transaction. A failed job has no transaction (no charge).

---

## Pillar Table

What enters at which lifecycle stage:

| Pillar | POC | Architecture | Beta | Production |
|--------|-----|-------------|------|------------|
| **ML Inference** | Experiment: Real-ESRGAN on Cloud Run, benchmark cost | Design API contract, output format (WebP), size limits | Production-quality FastAPI service, WebP conversion, error handling | GPU tier for 1920px+, model optimization |
| **Frontend** | -- | Page structure, upload flow design, polling strategy | Next.js app: upload, processing status, download, cost display, pricing page | Visual polish to 100%, performance optimization, SEO |
| **Auth** | -- | Magic link flow design, session strategy, token schema | Magic link implementation, session cookies, rate limiting | Security hardening, abuse protection |
| **Payments** | -- | Balance model, Stripe Checkout integration design, transaction schema | Stripe test mode, add funds flow, balance display, transaction history | Live Stripe, webhook hardening, receipt emails |
| **Storage** | -- | GCS bucket design, lifecycle policy, signed URL strategy | GCS integration, 24h auto-deletion, signed URL generation | Monitoring, cost tracking, backup policy review |
| **Deployment** | Cloud Run POC service (throwaway) | Two-service architecture, CI/CD design | Staging environment, Docker builds, Cloud Build pipeline | Production domain, SSL, CDN, monitoring, alerting |
| **Monitoring** | -- | Metrics design: cost tracking, job success rate | Basic logging, error tracking | Full observability: latency, cost reconciliation, alerts |

---

## Cost Model Reference

For quick reference across the codebase:

```
PIXEL_RATE_US       = 28        # microseconds per input pixel
COMPUTE_RATE_PER_S  = 0.000116  # USD per processing second (4 vCPU + 8 GiB)
PLATFORM_FEE_CENTS  = 5         # flat $0.005 per image
MAX_INPUT_PX        = 1024      # longest side, MVP limit

Estimate formula:
  processing_seconds = (width * height * PIXEL_RATE_US) / 1_000_000
  compute_cost_usd   = processing_seconds * COMPUTE_RATE_PER_S
  total_cost_usd     = compute_cost_usd + (PLATFORM_FEE_CENTS / 100)

Actual formula (post-processing):
  compute_cost_usd   = (X-Processing-Time-Ms / 1000) * COMPUTE_RATE_PER_S
  total_cost_usd     = compute_cost_usd + (PLATFORM_FEE_CENTS / 100)
```

---

## Open Questions for Beta

These do not need resolution now but should be addressed before Beta implementation:

1. **Email provider.** Resend vs SendGrid for magic link emails. Decide during Beta sprint.
2. **Minimum deposit amount.** $1.00 proposed. Could be lower to reduce friction.
3. **Free tier.** Should we give 1-3 free upscales to new users? Would demonstrate value. Deferred to CEO decision.
4. **GPU tier timeline.** When to add GPU support for 1920px+ images. Depends on user demand.
5. **Image resize option.** If a user uploads a 2000px image, should we offer to resize to 1024px and process, or just reject? The current design rejects; resize-and-confirm might be more user-friendly.

---

*Document produced during Architecture stage. Requires CEO gate approval before proceeding to Beta.*
