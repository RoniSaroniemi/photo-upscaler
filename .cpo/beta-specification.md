# Beta Specification — Honest Image Tools (Photo Upscaler)

*This document defines what Beta means for this project. The CPO reads this BEFORE writing any briefs. Every brief must trace back to a customer journey defined here.*

---

## What Beta Delivers

A working photo upscaling service where a real user can: discover the product, try it for free, sign up, add funds, upscale images, and download results — all with transparent pricing. ~80% visual fidelity. Not hardened or optimized.

---

## Customer Journey Table

*Each journey has: steps the user takes, what "working" means, and an acceptance test that PROVES it works.*

### Journey 1: Discovery — "What is this?"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Visit homepage | See product name, value proposition, pricing explanation, upload area |
| 2 | Read pricing | Understand: cost per image with breakdown (compute + platform fee) |
| 3 | See before/after example | Visual proof of upscaling quality |

**Acceptance test:**
```bash
# Playwright: screenshot homepage, verify key elements exist
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1280, 'height': 900})
    page.goto('http://localhost:3001')
    page.wait_for_load_state('networkidle')
    # Verify key content
    assert page.query_selector('text=/upscal/i'), 'Missing upscale mention'
    assert page.query_selector('text=/cost|price|\\$/i'), 'Missing pricing info'
    page.screenshot(path='evidence/journey-1-homepage.png')
    print('PASS: Homepage has product info + pricing')
    b.close()
"
```
**Evidence:** `evidence/journey-1-homepage.png` — READ the screenshot, verify it looks like a real product page.

---

### Journey 2: Free Trial — "Let me try before paying"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Upload an image (no account) | Image accepted, processing starts |
| 2 | Wait for processing | Progress indicator, then result |
| 3 | See upscaled result | Before/after comparison visible, download available |
| 4 | Download result | Actual image file downloads, dimensions are larger than input |
| 5 | Try again (2nd time) | Works (within free trial limit) |
| 6 | Try 3rd time | Rejected — prompted to sign up |

**Acceptance test:**
```bash
# Upload a test image without auth
curl -s -X POST http://localhost:3001/api/upscale \
  -F "file=@tests/fixtures/test-image.jpg" \
  -F "scale=2" | python3 -m json.tool
# Expected: {"job_id": "...", "download_url": "...", "cost": {...}}

# Download the result and verify dimensions
curl -s -o /tmp/upscaled.webp "<download_url_from_above>"
python3 -c "from PIL import Image; img=Image.open('/tmp/upscaled.webp'); print(f'Dimensions: {img.size}')"
# Expected: dimensions > input dimensions
```
**Evidence:** curl output showing job_id + download_url, and the actual dimensions of the downloaded file.

---

### Journey 3: Sign Up — "I want an account"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Click "Sign In" or "Sign Up" | See email input form |
| 2 | Enter email, submit | "Check your email" message |
| 3 | Receive email | Magic link email arrives (via Resend) |
| 4 | Click magic link | Redirected to app, logged in, session cookie set |
| 5 | See account state | Balance shows $0.00, name/email visible |

**Acceptance test:**
```bash
# Request magic link
curl -s -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com"}' | python3 -m json.tool
# Expected: {"message": "Check your email"}

# Check Resend dashboard or logs for delivered email
# Extract the magic link token from the email
# Verify the token:
curl -s "http://localhost:3001/api/auth/verify?token=<TOKEN>" -v 2>&1 | grep "Set-Cookie"
# Expected: Set-Cookie header with session token
```
**Evidence:** curl output showing email sent + Set-Cookie header from verify endpoint.

---

### Journey 4: Add Funds — "I want to pay"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Click "Add Funds" | See deposit options ($5, $10, $20) |
| 2 | Choose amount, proceed | Redirected to Stripe Checkout |
| 3 | Complete payment (test mode) | Redirected back to app |
| 4 | See updated balance | Balance reflects deposit minus Stripe fee explanation |

**Acceptance test:**
```bash
# Create checkout session (authenticated)
curl -s -X POST http://localhost:3001/api/payments/checkout \
  -H "Cookie: session=<JWT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"amount": 500}' | python3 -m json.tool
# Expected: {"checkout_url": "https://checkout.stripe.com/..."}

# After completing checkout in test mode:
# Trigger webhook locally
stripe trigger checkout.session.completed
# Check balance updated
curl -s http://localhost:3001/api/payments/balance \
  -H "Cookie: session=<JWT_TOKEN>" | python3 -m json.tool
# Expected: {"balance": 500000} (microdollars)
```
**Evidence:** Checkout URL generated + webhook received + balance updated.

---

### Journey 5: Paid Upload — "Upscale with my balance"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Upload image (logged in) | Processing starts, cost estimate shown |
| 2 | See cost breakdown | "Compute: $X, Platform: $Y, Total: $Z" |
| 3 | Processing completes | Before/after comparison, download button |
| 4 | Check balance | Balance decreased by the exact cost shown |
| 5 | Download result | Image downloads, dimensions larger than input |

**Acceptance test:**
```bash
# Upload with auth
curl -s -X POST http://localhost:3001/api/upscale \
  -H "Cookie: session=<JWT_TOKEN>" \
  -F "file=@tests/fixtures/test-image.jpg" \
  -F "scale=2" | python3 -m json.tool
# Expected: {"job_id": "...", "cost": {"compute": ..., "platform": ..., "total": ...}, "download_url": "..."}

# Check balance decreased
curl -s http://localhost:3001/api/payments/balance \
  -H "Cookie: session=<JWT_TOKEN>" | python3 -m json.tool
# Expected: balance decreased by cost.total
```
**Evidence:** Upload response with cost breakdown + balance before and after.

---

### Journey 6: Job History — "My previous uploads"

| Step | User Action | Expected Result |
|------|------------|-----------------|
| 1 | Navigate to "My Jobs" / history page | See list of previous uploads |
| 2 | Click a job | See details: original size, upscaled size, cost, date |
| 3 | Re-download | Download link works (if within expiry) |

**Acceptance test:**
```bash
curl -s http://localhost:3001/api/upscale/jobs \
  -H "Cookie: session=<JWT_TOKEN>" | python3 -m json.tool
# Expected: array of jobs with id, status, cost, timestamps
```
**Evidence:** Jobs list response showing at least 1 completed job.

---

### Journey 7: Error Handling — "What happens when things go wrong?"

| Scenario | Expected Result |
|----------|-----------------|
| Upload non-image file (.pdf) | Clear error: "Please upload an image file (JPG, PNG, WebP)" |
| Upload image > size limit | Clear error with the limit stated |
| Upload with insufficient balance | Clear error: "Insufficient balance. Your balance: $X. This image costs: $Y. Add funds." |
| Upload when inference service is down | Clear error, no money deducted, no trial slot consumed |
| Invalid magic link token | Clear error, redirect to login page |

**Acceptance test:**
```bash
# Non-image file
curl -s -X POST http://localhost:3001/api/upscale \
  -F "file=@tests/fixtures/test.pdf" | python3 -m json.tool
# Expected: {"error": "..."} with helpful message, NOT a 500

# Insufficient balance (use account with $0)
curl -s -X POST http://localhost:3001/api/upscale \
  -H "Cookie: session=<JWT_TOKEN_ZERO_BALANCE>" \
  -F "file=@tests/fixtures/test-image.jpg" | python3 -m json.tool
# Expected: {"error": "Insufficient balance", "balance": 0, "cost": ...}
```
**Evidence:** Error responses for each scenario — clear, helpful, no 500s.

---

## Quality Bar

- **Every journey must pass at Level 3** (flow works end-to-end) before Beta gate
- **UI visual fidelity: ~80%** — functional and recognizable, not pixel-perfect
- **Evidence for every journey** must be captured and included in the gate package
- **Known issues** must be documented honestly — "this works" vs "this is untested"

---

## What NOT to Build in Beta

- Performance optimization (cold start is fine)
- Admin dashboard
- Analytics / usage reporting
- Multiple upscaling models (one model is enough)
- Social sharing features
- API access for developers
- Batch upload
- Custom domain deployment (localhost/staging is fine)

---

## Known Issues from Previous CPO (status as of gate)

| Issue | Status | Notes |
|-------|--------|-------|
| Stripe webhook 401 | Fixed (PR #19) — needs re-verification |
| Trial race condition | Fixed (PR #19) — atomic upsert restored |
| File extension mismatch (PNG saved as .webp) | Open — cosmetic, Beta acceptable |
| Cross-project service account | Open — deployment concern, not Beta |
| Cloud Build pipeline broken | Open — deployment stage |
| UI preview of upscaled image not shown | Open — needs Playwright verification |
| Magic link flow untested end-to-end | Unknown — needs Journey 3 test |
| Trial slot consumed on failed upload | Fixed (PR #18) — needs re-verification |

---

## Test Fixtures Required

Before any briefs are dispatched, ensure these exist in the repo:
- `tests/fixtures/test-image.jpg` — a small test image (e.g., 640x480)
- `tests/fixtures/test-large.jpg` — an image near the size limit
- `tests/fixtures/test.pdf` — a non-image file for error testing
- `scripts/e2e-test.sh` — executable script that runs all 7 journey tests

---

*The new CPO reads this before writing any briefs. Every brief must reference which journey(s) it addresses and include the journey's acceptance test.*
