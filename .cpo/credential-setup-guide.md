# Credential Setup Guide — Honest Image Tools

*Everything the CPO needs to start dispatching Beta briefs. ~15 minutes total.*

---

## What We Need

| Service | What | Used For | Env Variable |
|---------|------|----------|-------------|
| Neon | Database connection string | Users, balances, transactions, jobs | `DATABASE_URL` |
| Resend | API key | Magic link auth emails | `RESEND_API_KEY` |
| Stripe | Secret key | Payment processing (server-side) | `STRIPE_SECRET_KEY` |
| Stripe | Publishable key | Payment form (client-side) | `STRIPE_PUBLISHABLE_KEY` |
| Stripe | Webhook secret | Verifying webhook signatures | `STRIPE_WEBHOOK_SECRET` |

All keys go into `.env.local` at the project root. This file is gitignored.

---

## 1. Neon — Serverless Postgres (~5 min)

### Sign Up

1. Go to **https://console.neon.tech/signup**
2. Sign in with your **Google account** (easiest), GitHub, or email/password
3. No credit card required

### Create a Project

1. After sign-up, Neon walks you through creating your first **Project**
2. Choose:
   - **Project name:** `honest-image-tools` (or anything you like)
   - **Region:** `us-east-2` (AWS) — closest to our Cloud Run in `us-central1`
   - **Postgres version:** latest (16+)
3. A default database `neondb` and a default role are created automatically

### Get the Connection String

1. On the project dashboard, click the **"Connect"** button (top of page)
2. A modal shows the connection string — copy it
3. It looks like:
   ```
   postgresql://alex:AbC123dEf@ep-cool-darkness-a1b2c3d4-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Make sure **connection pooling is ON** (the hostname should contain `-pooler`) — this is the default and works best with Cloud Run's serverless model

### Free Tier Limits

- **100 compute-hours/month** (scales to zero after 5 min idle — plenty for Beta)
- **0.5 GB storage** per project
- Auto-scaling up to 2 CU (1 vCPU + 4 GB RAM)
- No credit card needed

---

## 2. Resend — Transactional Email (~3 min for testing, +10 min for custom domain)

### Sign Up

1. Go to **https://resend.com/signup**
2. Create an account (email/password or GitHub)
3. No credit card required

### Get an API Key

1. Go to **API Keys**: https://resend.com/api-keys
2. Click **"Create API Key"**
3. Name it: `honest-image-tools`
4. Permission: **Sending access** (all that's needed for magic links)
5. Click create and **copy the key immediately** — you can only see it once
6. It looks like: `re_xxxxxxxxxxxxxxxxxxxxxxxxx`

### Testing Without a Custom Domain

For development/testing, you can send from `onboarding@resend.dev` immediately — **no domain setup needed**. The limitation: you can only send to your own email address (the one you signed up with). This is fine for testing magic links on yourself.

### Custom Domain (needed before real users)

When ready to send from `auth@yourdomain.com`:

1. Go to **Domains** in the Resend dashboard
2. Add your domain (e.g., `honestimagetools.com`)
3. Resend gives you DNS records to add:
   - **SPF record** — authorizes Resend to send for your domain
   - **DKIM record** — proves email authenticity
4. Add these in your DNS provider (Cloudflare, Namecheap, etc.)
5. Click **"Verify DNS Records"** in Resend
6. Once verified, send from any address at that domain

**For Beta testing:** The `onboarding@resend.dev` sender is enough. We'll add a custom domain before Production.

### Free Tier Limits

- **100 emails/day** (3,000/month) — plenty for Beta
- 1 custom domain
- 5 requests/second API rate limit

---

## 3. Stripe — Payments (~5 min)

### Sign Up / Access Test Mode

1. Go to **https://dashboard.stripe.com/register** (or log into existing account)
2. You do **NOT** need to activate your account or provide business details to use test mode
3. Test mode is enabled by default — look for the **"Test mode"** toggle in the dashboard header

### Get Test API Keys

1. Go to **Developers → API keys**: https://dashboard.stripe.com/test/apikeys
2. You'll see:
   - **Publishable key:** `pk_test_...` — visible immediately, copy it
   - **Secret key:** Click **"Reveal test key"** to see `sk_test_...` — copy it
3. These are test-mode keys — no real charges, no real money

### Get the Webhook Signing Secret

You have two options:

#### Option A: Stripe CLI (recommended for local development)

1. Install: `brew install stripe/stripe-cli/stripe`
2. Login: `stripe login` (opens browser for auth)
3. Forward events to your local app:
   ```bash
   stripe listen --forward-to localhost:3000/api/balance/webhook
   ```
4. The CLI prints: `Your webhook signing secret is whsec_...` — copy this
5. To test: `stripe trigger checkout.session.completed`

#### Option B: Dashboard Webhook (for deployed staging/production)

1. Go to **Developers → Webhooks**: https://dashboard.stripe.com/test/webhooks
2. Click **"Add endpoint"**
3. Enter your endpoint URL: `https://your-staging-url.run.app/api/balance/webhook`
4. Select events: `checkout.session.completed`
5. Click create
6. Click the endpoint → **"Reveal secret"** → copy `whsec_...`

### Test Card Numbers

When testing payments in the browser:
- **Success:** `4242 4242 4242 4242`
- **Requires 3D Secure:** `4000 0025 0000 3155`
- **Declined:** `4000 0000 0000 9995`
- Use any future expiry, any 3-digit CVC, any postal code

---

## Putting It All Together

Create `.env.local` in the project root:

```bash
# Neon Postgres
DATABASE_URL="postgresql://USER:PASS@ep-xxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"

# Resend
RESEND_API_KEY="re_xxxxxxxxxxxxxxxxxxxxxxxxx"

# Stripe (test mode)
STRIPE_SECRET_KEY="sk_test_xxxxxxxxxxxxxxxxxxxxxxxxx"
STRIPE_PUBLISHABLE_KEY="pk_test_xxxxxxxxxxxxxxxxxxxxxxxxx"
STRIPE_WEBHOOK_SECRET="whsec_xxxxxxxxxxxxxxxxxxxxxxxxx"

# App
JWT_SECRET="$(openssl rand -hex 32)"
NEXT_PUBLIC_APP_URL="http://localhost:3000"
INFERENCE_SERVICE_URL="https://esrgan-poc-132808742560.us-central1.run.app"
```

The JWT_SECRET can be generated by running:
```bash
openssl rand -hex 32
```

### Verification Checklist

After filling in `.env.local`:

- [ ] Neon: `psql "$DATABASE_URL" -c "SELECT 1"` returns `1` (or test from Neon console SQL editor)
- [ ] Resend: `curl -X POST https://api.resend.com/emails -H "Authorization: Bearer $RESEND_API_KEY" -H "Content-Type: application/json" -d '{"from":"onboarding@resend.dev","to":"YOUR_EMAIL","subject":"Test","html":"<p>Works!</p>"}'`
- [ ] Stripe: `curl https://api.stripe.com/v1/customers -u "$STRIPE_SECRET_KEY:"` returns a customer list (empty is fine)

---

## What Happens Next

Once `.env.local` is populated:

1. **Brief 1** (Foundation + Database Schema) — scaffolds Next.js app, runs Drizzle migrations against Neon
2. **Briefs 2, 3, 4** (parallel) — inference service (done), auth (Resend), payments (Stripe)
3. **Briefs 5, 6, 7** (sequential) — upload flow, frontend, deployment

The CPO dispatches these automatically. You'll be pinged at the Beta gate with a demo to review.
