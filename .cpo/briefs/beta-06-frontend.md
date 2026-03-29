# Brief — Frontend Pages + Free Trial

**Scope:** Build all user-facing pages (landing, pricing, account, upload, job status) and implement the free trial system (1-2 free upscales per IP).
**Branch:** `feature/frontend` — new worktree
**Effort estimate:** XL (~4 hours)
**Risk:** Medium
**Affects:** `frontend/src/app/`, `frontend/src/components/`, `frontend/src/app/api/`
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Node.js >= 20: `node --version`
- [ ] Brief 1 (Foundation) merged: Next.js scaffold, database schema
- [ ] Brief 3 (Auth) merged: login/logout flow working
- [ ] Brief 4 (Payments) merged: balance display, add funds flow
- [ ] Brief 5 (Upload Flow) merged: POST /api/upscale, pricing APIs working

### Credentials & Access
- [ ] All `.env.local` variables from prior briefs

### Verification Capability
- [ ] Can verify via: `npm run dev` + manual walkthrough of all pages
- [ ] Can verify via: Playwright tests (screenshot each page state)
- [ ] Can verify free trial: use incognito/different browser to test IP-based limits

### Human Dependencies
- [ ] None — fully autonomous

---

## 1. The Problem (Why)

The API backend is complete but there's no user interface. Users need an intuitive, honest web experience that:
1. Lets them upload an image and see the cost BEFORE processing
2. Shows the real cost breakdown AFTER processing (the key differentiator)
3. Lets them manage their balance and view transaction history
4. Gives 1-2 free upscales to demonstrate value before requiring payment

---

## 2. The Solution (What)

### 2.1 Landing Page (`/`)

Server + client component hybrid.

**Above the fold:**
- Headline: "Upscale your photos. See exactly what it costs."
- Subheadline: "No subscriptions. No hidden fees. Just honest pricing."
- Upload area: drag-and-drop or click-to-select file input
- When image selected: show thumbnail, dimensions, and estimated cost (fetched from `/api/pricing/estimate`)

**Below the fold:**
- How it works (3 steps: Upload → Process → Download)
- Cost examples table (from `/api/pricing/formula`)
- Comparison with competitors (honest pricing vs subscription bundles)

**Upload interaction:**
1. User selects/drops an image
2. JS reads image dimensions client-side
3. Fetches cost estimate from `/api/pricing/estimate?width=W&height=H`
4. Shows: "Estimated cost: ~$0.008 (Compute: $0.003 + Platform: $0.005)"
5. If dimensions > 1024px: show error "Image too large. Max 1024px on longest side."
6. If user is logged in with sufficient balance: show "Upscale now" button
7. If user is logged in with insufficient balance: show "Add funds ($X needed)" button
8. If user is not logged in AND has free trial remaining: show "Upscale free (X of 2 remaining)" button
9. If user is not logged in AND no free trial: show "Sign in to continue" button

### 2.2 Processing State

After user clicks "Upscale now" (or free trial):

1. POST to `/api/upscale` with the file
2. Show processing UI:
   - Estimated time remaining (countdown from estimated_seconds)
   - Animated progress bar (reaches ~90% at estimated time, then holds)
   - Elapsed time counter
   - "Processing..." status text
3. If request stays open (synchronous): wait for response
4. If response received: show completion UI

### 2.3 Completion State

On successful upscale:
```
✓ Upscale Complete

[Before/After comparison — side by side thumbnails]

Input:  1024 × 768 → Output: 4096 × 3072

Cost Breakdown
  Compute:      $0.003    (22.0s processing)
  Platform fee: $0.005
  ─────────────────────
  Total:        $0.008    deducted from balance

[Download (WebP, 2.3 MB)]  [Upscale another]
```

On failure:
```
✗ Processing Failed

Something went wrong. No charge was applied to your balance.

[Try again]  [Contact support]
```

### 2.4 Pricing Page (`/pricing`)

Server component. Static content.

- The pricing formula explained in plain English
- Interactive calculator: enter dimensions → see cost
- Cost examples table at common resolutions
- Comparison: "How we compare" — our $0.008 vs competitor $0.09-0.20
- FAQ: minimum deposit, how balance works, what happens to unused balance

### 2.5 Auth Pages (`/auth/login`, `/auth/verify`)

Already built in Brief 3, but need styling:
- `/auth/login`: Clean email input with "Send magic link" button
- `/auth/verify`: Loading state while verifying, then redirect

### 2.6 Account Page (`/account`)

Server component with client components for interactivity.

- Current balance display: "$4.97 remaining (~620 upscales)"
- "Add Funds" button → links to `/account/add-funds`
- Recent transactions list (from `/api/balance/transactions`)
  - Each entry shows: date, type (deposit/charge), amount, description
  - Charges show the cost breakdown inline
- Recent jobs list (from `/api/upscale/jobs`)
  - Each entry shows: date, input→output size, cost, status
  - Completed jobs within 24h have "Download" link
  - Jobs older than 24h show "Expired"

### 2.7 Add Funds Page (`/account/add-funds`)

Client component.

- Preset buttons: $5, $10, $25
- Shows: "~625 upscales" / "~1,250 upscales" / "~3,125 upscales" (calculated from average cost)
- Note: "Minimum deposit: $5.00. Stripe processing applies."
- Button click → POST `/api/balance/add-funds` → redirect to Stripe Checkout
- Success return: show "Balance updated!" toast

### 2.8 Job Detail Page (`/jobs/:id`)

Client component with polling.

- Shows job status (pending → processing → complete/failed)
- Processing: progress bar + elapsed time
- Complete: cost breakdown + download link
- Failed: error message + "no charge" confirmation

### 2.9 Free Trial System

**API: POST /api/upscale** modification:
- If user is NOT authenticated, check `free_trial_uses` table
- Hash the client IP with SHA-256
- Look up `uses_count` for this IP hash
- If uses_count < 2: allow the upscale without balance check
  - Increment uses_count (INSERT or UPDATE)
  - Process normally, skip balance deduction
  - Return result with `"trial": true, "remaining": N` in response
- If uses_count >= 2: return 401 "Free trial exhausted. Sign in and add funds."

**API: GET /api/pricing/trial-status** (no auth):
- Returns `{ "remaining": 2, "total": 2 }` or `{ "remaining": 0, "total": 2 }` based on IP

**Frontend integration:**
- On landing page, check trial status
- Show "Free — X of 2 remaining" badge on the upscale button
- After free trial exhausted: show "Sign in to continue" with value pitch

**IP extraction:**
- Use `x-forwarded-for` header (set by Cloud Run)
- Fallback to connection IP
- Hash with SHA-256 before storing (privacy)

### 2.10 Navigation + Layout

- Sticky header: Logo | Pricing | Account (if logged in) / Sign In (if not)
- Footer: minimal — "Honest Image Tools" + link to pricing
- Mobile-responsive: Tailwind breakpoints
- Dark mode: Not for Beta (defer)

---

## 3. Design Alignment

Implements ADR-006 (frontend architecture) and ADR-008 (free trial, new). The cost display is the product's core differentiator — it must be prominent and clear on every completed job.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Beta

**Stage-appropriate work in this brief:**
- Full frontend is a Beta deliverable
- Free trial is CEO-approved scope

**Out of scope for this stage:**
- Dark mode
- Image comparison slider (before/after)
- Multiple upload queue
- SEO optimization
- Analytics/tracking
- Social sharing

---

## 4. Implementation Plan

### Phase 1: Layout + Navigation
- Create shared layout with header/footer
- Implement auth-aware navigation (login state)
- Set up Tailwind theme (colors, spacing)
- Mobile-responsive skeleton

### Phase 2: Free Trial API
- Create `free_trial_uses` table operations
- Modify POST /api/upscale to support unauthenticated free trial
- Create GET /api/pricing/trial-status
- Test: 2 free upscales work, 3rd is rejected

### Phase 3: Landing Page + Upload Flow
- Build landing page with upload area
- Client-side dimension reading + cost estimation
- Processing state with progress bar
- Completion state with cost breakdown display
- Free trial flow integration

### Phase 4: Account + Payments Pages
- Account page with balance + transactions
- Add Funds page with Stripe integration
- Job history with download links

### Phase 5: Pricing Page
- Pricing formula explanation
- Interactive calculator
- Competitor comparison
- FAQ section

### Phase 6: Polish + Testing
- Error states for all pages
- Loading states
- Mobile testing
- Playwright screenshot tests of each page state

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| Landing page renders with upload area | Basic page works |
| Select image → cost estimate shows | Client-side estimation works |
| Free trial: first upload processes without auth | Free trial works |
| Free trial: 3rd upload shows "sign in" | Trial limit enforced |
| Upload with balance → processing → completion | Full flow works |
| Completion shows cost breakdown | Core differentiator visible |
| Download link works | GCS signed URL works through UI |
| Account page shows balance + transactions | Account page works |
| Add funds → Stripe checkout → balance updated | Payment flow works end-to-end |
| Pricing page calculator shows correct estimates | Pricing calculator works |
| Mobile viewport renders correctly | Responsive design works |
| Playwright screenshots of all page states | Visual verification captured |

### Acceptance Criteria
- [ ] Complete user journey: land → try free → see cost → sign up → add funds → upscale paid → download
- [ ] Cost breakdown is prominently displayed on every completed job
- [ ] Free trial gives 1-2 upscales without requiring sign-in
- [ ] Pricing page clearly explains the pricing model
- [ ] Account page shows balance, transactions, and job history
- [ ] All pages are mobile-responsive
- [ ] Error states are handled gracefully (not raw error messages)
- [ ] Playwright screenshots captured for all page states

---

## 7. What This Does NOT Include

- Dark mode
- Image comparison slider (before vs after)
- Drag-and-drop from clipboard
- Multiple image upload queue
- SEO meta tags + sitemap
- Analytics (Google Analytics, Plausible, etc.)
- Social sharing buttons
- Terms of service / privacy policy pages
- Contact/support page

---

## 8. Challenge Points

- [ ] **Free trial abuse:** Assume IP-based limiting is sufficient for Beta. VPN/proxy users can get unlimited free trials. Accept this risk — the cost per image is $0.003-0.008, so abuse is cheap. Monitor and add fingerprinting later if needed.
- [ ] **Client-side image dimension reading:** Assume `new Image()` in the browser can read dimensions of the selected file before upload. Verify this works for all supported formats (JPEG, PNG, WebP). Large files may be slow to load in memory.
- [ ] **Synchronous upload UX:** The request stays open for 10-47s. Assume browsers don't timeout on long-running fetch requests. If issues arise, switch to async with polling (the job APIs are already built for this pattern).

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browser timeout on long uploads | User sees error despite success | Show "still processing" message; implement polling fallback |
| Free trial IP tracking bypassed | Revenue loss on free images | Cost is $0.003-0.008; acceptable for Beta. Monitor. |
| Mobile upload issues | Poor mobile experience | Test on iOS Safari + Android Chrome |
| Tailwind styling inconsistencies | Unprofessional appearance | Use consistent spacing scale; screenshot tests |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/frontend`
2. `gh pr create --title "PRJ-001: Frontend pages + free trial system" --body "..." --base main --head feature/frontend`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Fully autonomous.** All dependencies (Briefs 1-5) are merged. No human interaction needed.

---

*Brief version: 1.0 — 2026-03-29*
