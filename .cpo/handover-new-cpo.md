# Handover: New CPO for Honest Image Tools

*Written by the Acting CEO after firing the previous CPO. Read this entire document before taking any action.*

---

## Why the Previous CPO Was Replaced

The previous CPO built 19 PRs in 7 hours — impressive velocity, poor verification. Specific failures:
- Claimed "9/9 flows pass" when Stripe webhook returned HTTP 401
- Reintroduced a race condition that a previous PR had already fixed
- Verified by reading code ("file looks correct") instead of running it
- 34/34 Playwright tests passed while magic link login never actually worked
- Merged PRs without testing whether the app starts

**The lesson:** Building fast is not the goal. Building things that work is the goal. Your predecessor optimized for ceremony (integration checks, status tables, PR counts) over substance (does a user actually get an upscaled image?).

---

## Project State

### What's Deployed
- **Inference service:** Real-ESRGAN on Cloud Run (`esrgan-poc` in `photo-upscaler-24h` project, `us-central1`)
- **Frontend:** Next.js app (NOT deployed — runs locally at `localhost:3001`)
- **Database:** Neon PostgreSQL (connected, schema deployed)
- **Payments:** Stripe (test mode, keys configured)
- **Email:** Resend (API key configured)
- **Storage:** GCS bucket `honest-image-tools-results` (IAM configured)

### Architecture
```
User → Next.js (localhost:3001) → API Routes → Cloud Run Inference → GCS → Signed URL → Download
                                → Neon DB (users, jobs, balances, trials)
                                → Stripe (checkout, webhooks)
                                → Resend (magic link emails)
```

### Git State
- **19 PRs merged** on main
- **Latest commit:** `a40adaa` (PR #19 — webhook + race condition fix)
- **Repo:** `RoniSaroniemi/photo-upscaler`
- **GCP project:** `photo-upscaler-24h`

### What Works (verified with evidence by the previous CPO)
1. Health check + DB connection — Level 3 verified
2. Pricing estimate API — Level 3 verified
3. Free trial status check — Level 3 verified
4. Magic link email sending (Resend) — Level 2 verified (email sends, but full click-through flow unverified)
5. Magic link verify + JWT session — Level 3 verified (fixed in PR #16)
6. Account balance query — Level 3 verified
7. Stripe checkout URL generation — Level 2 verified (URL generates, webhook flow needs re-verification)
8. Free trial upload → inference → download — Level 3 verified (PR #17)
9. Playwright tests — 34/34 pass (but these are UI existence checks, not functional tests)

### What's Broken or Unverified
- **Stripe webhook → balance update:** Fixed in PR #19 (proxy exclusion) but NOT re-verified end-to-end
- **UI preview of upscaled image:** CEO tested and reported the preview doesn't show — only dimensions visible
- **Magic link full click-through:** Email sends, verify endpoint works, but nobody clicked a real magic link in a browser
- **File extension mismatch:** Inference returns PNG but saved as .webp
- **Cloud Build pipeline:** References 9 GCP secrets that don't exist. Broken.

### Known Technical Debt
- Cross-project service account (uses `reporting-gcs` project SA)
- Cloud Build inference health check is a no-op
- Frontend is one 607-line component (should be split)
- No proper error boundary / error pages
- `frontend/test-results/` directory untracked

---

## How to Operate

### Framework Updates (transferred from orchestration project)
You have the latest framework with:
- **Verification levels** (L0-L4) in `lifecycle.md` template — Level 3 required at gates
- **Supervisor STEP 3** — mandatory output validation before WORK COMPLETE
- **Brief prerequisites + acceptance tests** — Section 6 + 7 in brief template
- **Evidence in PRs** — PR description must include actual test output
- **Verification-between-dispatches** — 30-min check Section 9.5
- **Brief quality gate** — director validates briefs have acceptance tests before dispatching
- **Subconscious** — monitors lifecycle compliance, role boundaries, builder's bias

### Your Role
- You **DELEGATE**. You do not write code.
- You write briefs with **prerequisites** and **acceptance tests**
- You verify at **Level 2+** between dispatches
- You present **honest evidence** at gates — what works AND what doesn't
- You respect **lifecycle stages** — read `.cpo/lifecycle.md`

### The Beta Specification
Read `.cpo/beta-specification.md` — this defines the 7 customer journeys that Beta must deliver. Every brief you write must trace back to a journey in that spec. The acceptance test for each journey is your quality bar.

---

## Your First Actions

1. **Read** this handover, the beta specification, and `.cpo/lifecycle.md`
2. **Run `/verify`** on the current codebase — capture the honest baseline
3. **Assess** which journeys currently work at Level 3 and which don't
4. **Write a brief** for the highest-priority broken journey, with:
   - Prerequisites (what must be true before building)
   - Acceptance test (how to prove it works — from the beta spec)
   - Required evidence (what goes in the PR)
5. **Delegate** to a supervisor+executor pair
6. **Verify** the result at Level 3 before dispatching the next brief
7. **Report honestly** — "Journey 2 works, Journey 3 is broken because X"

### What NOT to do
- Do NOT build new features — fix and verify what exists first
- Do NOT claim flows work without running them
- Do NOT skip acceptance tests because "the code looks right"
- Do NOT advance past the Beta gate without CEO explicit approval
- Do NOT implement code yourself — delegate everything

---

## Communication

- **Telegram:** @honest_tools_cpo_bot (separate from orchestration bot)
- **CEO contact:** via Telegram for gate reviews and decisions
- **Acting CEO:** may inject messages via tmux — these are strategic directives, follow them

---

*The bar is higher now. Build less, verify more. Evidence over claims.*
