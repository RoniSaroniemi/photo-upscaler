# Brief — Payments + Balance System (Stripe)

**Scope:** Implement Stripe Checkout for deposits, balance management in microdollars, webhook handling, and transaction history.
**Branch:** `feature/payments` — new worktree
**Effort estimate:** L (~2 hours)
**Risk:** Medium (Stripe webhook setup, minimum deposit math)
**Affects:** `frontend/src/app/api/balance/`, `frontend/src/lib/stripe/`, `frontend/src/app/account/`
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Node.js >= 20: `node --version`
- [ ] Brief 1 (Foundation) completed: database schema deployed with microdollar columns

### Credentials & Access
- [ ] Stripe account created (test mode)
- [ ] `STRIPE_SECRET_KEY` (test mode): `sk_test_...`
- [ ] `STRIPE_PUBLISHABLE_KEY` (test mode): `pk_test_...`
- [ ] `STRIPE_WEBHOOK_SECRET`: from Stripe CLI or dashboard webhook setup
- [ ] All stored in `.env.local`

### Verification Capability
- [ ] Can verify via: Stripe test mode + test card `4242424242424242`
- [ ] Can verify webhooks via: `stripe listen --forward-to localhost:3000/api/balance/webhook`
- [ ] Install Stripe CLI: `brew install stripe/stripe-cli/stripe`

### Human Dependencies
- [ ] Stripe account + API keys — needed before any payment work
- [ ] Agent can install Stripe CLI locally for webhook testing

---

## 1. The Problem (Why)

Users need to deposit real money (USD) into a prepaid balance before upscaling images. This is the core business model — transparent, pay-what-it-costs pricing. The balance system must be ACID-safe (no negative balances, no lost deposits) and use microdollars for sub-cent precision.

---

## 2. The Solution (What)

### 2.1 Stripe Checkout Session for Deposits

**POST /api/balance/add-funds** (auth required)

Request: `{ "amount_cents": 500 }` (Stripe uses cents for Checkout amounts)

Flow:
1. Validate: amount >= 500 cents ($5.00 minimum deposit)
2. Create Stripe Checkout Session:
   - `mode: "payment"`
   - `line_items: [{ price_data: { currency: "usd", unit_amount: amount_cents, product_data: { name: "Account Balance Top-Up" } }, quantity: 1 }]`
   - `success_url: {BASE_URL}/account?deposit=success`
   - `cancel_url: {BASE_URL}/account/add-funds?deposit=cancelled`
   - `metadata: { user_id, amount_cents }`
   - `client_reference_id: user_id`
3. Return: `{ checkout_url, session_id }`

**Minimum deposit: $5.00** (500 cents). Rationale:
- Stripe fee on $5: $0.30 + 2.9% = $0.445 → 8.9% overhead (acceptable)
- Stripe fee on $1: $0.30 + 2.9% = $0.329 → 32.9% overhead (too high)
- $5 buys ~625-833 upscales at $0.006-0.008 each — substantial value

Preset deposit options in UI: $5, $10, $25.

### 2.2 Webhook Handler

**POST /api/balance/webhook** (no auth — Stripe calls this)

1. Verify Stripe signature using `STRIPE_WEBHOOK_SECRET`
2. Handle `checkout.session.completed` event:
   a. Extract `user_id` from `client_reference_id`
   b. Extract `amount_cents` from session `amount_total`
   c. Convert to microdollars: `amount_microdollars = amount_cents * 10_000`
   d. **Idempotency check:** Look for existing transaction with this `stripe_checkout_session_id`. If found, skip (already processed).
   e. In a single SQL transaction:
      - INSERT into `transactions` (type: "deposit", amount_microdollars: positive, stripe_checkout_session_id)
      - UPDATE `balances` SET `amount_microdollars = amount_microdollars + deposit_amount`
   f. Return `{ received: true }`
3. Ignore all other event types (return 200 anyway)

### 2.3 Balance API

**GET /api/balance** (auth required)

Returns:
```json
{
  "balance_microdollars": 5000000,
  "formatted": "$5.00",
  "currency": "USD"
}
```

### 2.4 Transaction History

**GET /api/balance/transactions** (auth required)

Query params: `?limit=20&offset=0`

Returns:
```json
{
  "transactions": [
    {
      "id": "txn_...",
      "type": "deposit",
      "amount_microdollars": 5000000,
      "formatted_amount": "$5.00",
      "description": "Added funds via Stripe",
      "created_at": "2026-03-29T10:00:00Z"
    },
    {
      "id": "txn_...",
      "type": "charge",
      "amount_microdollars": -8000,
      "formatted_amount": "-$0.008",
      "description": "Upscale: 1024x768 → 4096x3072",
      "job_id": "job_...",
      "cost_breakdown": {
        "compute_microdollars": 3000,
        "platform_fee_microdollars": 5000,
        "total_microdollars": 8000
      },
      "created_at": "2026-03-29T10:05:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

### 2.5 Balance Deduction Utility

Create a reusable function for atomic balance deduction (used by the upscale API in Brief 5):

```typescript
async function deductBalance(userId: string, amount_microdollars: number, jobId: string, description: string): Promise<boolean>
```

This executes the atomic SQL transaction from the architecture doc:
```sql
BEGIN;
  UPDATE balances SET amount_microdollars = amount_microdollars - $cost
  WHERE user_id = $user_id AND amount_microdollars >= $cost;
  -- If 0 rows updated → ROLLBACK (insufficient balance)
  INSERT INTO transactions (...) VALUES (...);
COMMIT;
```

### 2.6 Formatting Utility

Create `src/lib/pricing/format.ts`:
- `formatMicrodollars(amount: number): string` → "$0.008", "$5.00"
- `centsToMicrodollars(cents: number): number` → multiply by 10,000
- `microdollarsToCents(microdollars: number): number` → divide by 10,000

---

## 3. Design Alignment

Implements ADR-004 (cost display) with the microdollar unit system. Stripe Checkout Session is the simplest integration path — no custom payment forms, no PCI compliance burden.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Architecture → Beta transition

**Stage-appropriate work in this brief:**
- Payments is a Beta pillar (see lifecycle.md)
- Stripe test mode only

**Out of scope for this stage:**
- Live Stripe (Production stage)
- Refund automation
- Receipt emails
- Subscription billing
- Multiple currency support

---

## 4. Implementation Plan

### Phase 1: Stripe SDK + Config
- `npm install stripe`
- Create `src/lib/stripe/index.ts` — Stripe client initialization
- Create `src/lib/stripe/checkout.ts` — create checkout session
- Create `src/lib/pricing/format.ts` — microdollar formatting utilities

### Phase 2: API Routes
- Create `POST /api/balance/add-funds` — creates Stripe Checkout Session
- Create `POST /api/balance/webhook` — handles checkout.session.completed
- Create `GET /api/balance` — returns current balance
- Create `GET /api/balance/transactions` — returns transaction history

### Phase 3: Balance Deduction
- Create `src/lib/stripe/balance.ts` — `deductBalance()` atomic function
- Test: deduction with sufficient balance succeeds
- Test: deduction with insufficient balance fails (CHECK constraint)
- Test: concurrent deductions don't cause negative balance

### Phase 4: Add Funds UI
- Create `/account/add-funds` page — preset buttons ($5, $10, $25), redirect to Stripe Checkout
- Display current balance on account page
- Show deposit success/cancelled state from URL params

### Phase 5: Webhook Testing
- Install Stripe CLI: `brew install stripe/stripe-cli/stripe`
- `stripe listen --forward-to localhost:3000/api/balance/webhook`
- Test with: `stripe trigger checkout.session.completed`
- Verify balance increases after webhook

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| POST /api/balance/add-funds with $5 → Stripe checkout URL | Checkout session creation works |
| POST /api/balance/add-funds with $1 → 400 error | Minimum deposit enforced |
| Stripe Checkout completed → balance increases by $5 | Webhook processing works |
| Duplicate webhook → balance only increases once | Idempotency works |
| GET /api/balance → shows correct balance | Balance query works |
| GET /api/balance/transactions → shows deposit | Transaction history works |
| deductBalance() with sufficient balance → success | Deduction works |
| deductBalance() with insufficient balance → failure | CHECK constraint works |
| Concurrent deductBalance() calls → no negative balance | ACID safety verified |

### Acceptance Criteria
- [ ] Stripe Checkout flow works with test card 4242...
- [ ] Balance credited after successful checkout (verified via webhook)
- [ ] Duplicate webhooks are idempotent (no double-credit)
- [ ] Balance can never go negative (DB CHECK constraint + app logic)
- [ ] Transaction history shows deposits and charges correctly
- [ ] Amounts display correctly in microdollars (e.g., "$0.008" not "$0.01")
- [ ] Minimum deposit of $5 enforced
- [ ] All amounts stored as INTEGER microdollars in database

---

## 7. What This Does NOT Include

- Live Stripe keys (test mode only)
- Refund flow
- Receipt emails
- Payout/withdrawal
- Multiple payment methods
- Subscription billing
- Stripe customer portal

---

## 8. Challenge Points

- [ ] **Stripe minimum charge:** Verify Stripe has no minimum charge amount in test mode. In live mode, some regions have minimums (e.g., $0.50 USD). Our $5 minimum deposit is well above this, but verify.
- [ ] **Webhook reliability in dev:** Assume Stripe CLI `listen` command reliably forwards webhooks to localhost. If flaky, may need to use Stripe's test event triggers.
- [ ] **Microdollar conversion precision:** Converting cents to microdollars is `* 10000` — verify no integer overflow. Max Stripe amount is $999,999.99 = 99,999,999 cents = 999,999,990,000 microdollars. This exceeds 32-bit INTEGER max (2,147,483,647). **Use BIGINT for amount_microdollars columns if deposits can be large.** In practice, deposits of $5-25 are fine with INTEGER, but the schema should use BIGINT for safety.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Webhook delivery fails | Deposit not credited | Stripe retries for up to 3 days; add manual reconciliation endpoint |
| Stripe API changes | Integration breaks | Pin stripe npm version |
| Integer overflow on microdollars | Corrupted balances | Use BIGINT; max $2.1M with INTEGER is likely fine for Beta |
| Race condition on balance deduction | Negative balance | DB CHECK constraint is the safety net; test concurrent deductions |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/payments`
2. `gh pr create --title "PRJ-001: Stripe payments + balance system" --body "..." --base main --head feature/payments`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Mostly autonomous.** Requires Stripe API keys from human. Stripe CLI can be installed by agent.

---

*Brief version: 1.0 — 2026-03-29*
