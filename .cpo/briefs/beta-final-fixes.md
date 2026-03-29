# Supervisor Brief — Final Beta Fixes: Trial Bug + Stripe Test + Commit

**Branch:** `fix/beta-final`
**Executor session:** `exec-final`

## 1. The Problem

Three items required before the Beta gate:
1. Free trial count increments BEFORE inference — if inference fails, user loses a trial slot for nothing
2. Stripe webhook flow (checkout.session.completed) has never been tested
3. Uncommitted operational files in the repo

## 2. Scope

Do ONLY these three things. Do NOT fix: file extension mismatch, service account cross-project, Cloud Build pipeline. Those are Production stage.

## 3. Implementation

### Fix 1: Trial decrement on failure

Read `frontend/src/app/api/upscale/route.ts`. Find where the free trial count is incremented. Currently it happens BEFORE the inference call. This means if inference fails or GCS upload fails, the user has lost a free trial slot.

**Fix:** Move the free trial increment (the atomic INSERT...ON CONFLICT upsert on `free_trial_uses`) to AFTER the inference succeeds and the result is stored. The flow should be:

```
1. Check trial remaining (SELECT, don't increment yet)
2. Run inference
3. Upload to GCS
4. Only NOW increment the trial count
5. Return result
```

If inference fails at step 2 or GCS fails at step 3, the trial count stays unchanged — user can retry.

Important: the check in step 1 needs to be safe against race conditions. Use `SELECT ... WHERE uses_count < 2` without incrementing — then do the atomic increment in step 4. Two concurrent requests could both pass the check, giving 3 uses instead of 2. That's acceptable for Beta (CEO confirmed VPN abuse is low-risk at our cost per image).

**Verify the fix:**
```bash
# Start dev server
cd /Users/roni-saroniemi/Github/photo-upscaler/frontend
cp ../.env.local .env.local
# Ensure these are in .env.local:
# INFERENCE_SERVICE_URL=https://esrgan-poc-132808742560.us-central1.run.app
# GCS_BUCKET_NAME=honest-image-tools-results
source .env.local
PORT=3001 npx next dev --port 3001

# Check trial status before
curl -s http://localhost:3001/api/pricing/trial-status

# Upload with a file that will FAIL inference (e.g., a text file renamed to .jpg)
echo "not an image" > /tmp/fake.jpg
curl -s -X POST -F "file=@/tmp/fake.jpg" http://localhost:3001/api/upscale

# Check trial status after — should be UNCHANGED
curl -s http://localhost:3001/api/pricing/trial-status
```

### Fix 2: Stripe webhook test

With the dev server running on port 3001:

```bash
# Terminal 1: start stripe listen
stripe listen --forward-to localhost:3001/api/balance/webhook

# Terminal 2: trigger test event
stripe trigger checkout.session.completed
```

Record:
- What stripe listen outputs (the webhook delivery)
- The response from your server (200 or error)
- Check DB for a transaction record:
  ```bash
  source .env.local && psql "$DATABASE_URL" -c "SELECT * FROM transactions ORDER BY created_at DESC LIMIT 3"
  ```

Note: the test event won't match a real user/session in our DB, so the webhook handler may log "session not found" or similar. That's OK — document what happens. The important thing is:
- Does the webhook endpoint receive the event? (stripe listen shows delivery)
- Does it verify the signature? (no 400/signature error)
- Does it attempt to process? (check server logs)

If the handler returns 200, that's PASS. If it returns 400 (signature mismatch), check that STRIPE_WEBHOOK_SECRET in .env.local matches the whsec_ from `stripe listen`.

### Fix 3: Commit everything

After fixes 1 and 2 are done:

```bash
cd /Users/roni-saroniemi/Github/photo-upscaler

# Stage all operational files, briefs, reports, and code fixes
git add \
  .cpo/ \
  .director/registry.json \
  .gitignore \
  frontend/ \
  poc/ \
  docs/

# Check what's staged — make sure no secrets (.env.local) are included
git status

# If .env.local appears, remove it:
git reset .env.local frontend/.env.local

# Commit
git commit -m "Beta final fixes: trial-on-success, Stripe webhook verified, operational files

- Fix: free trial count only increments after successful inference+GCS
- Test: Stripe checkout.session.completed webhook verified via CLI
- Commit: all operational files, briefs, evidence reports

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"

git push origin fix/beta-final
```

### Evidence Appendix

Append to `poc/e2e-real-report.md`:

```markdown
## Fix: Trial Decrement on Failure

### Before fix
Trial count incremented before inference. Failed upload consumed a trial slot.

### After fix
Trial count only increments after successful inference + GCS upload.

### Verification
- Trial status before failed upload: {remaining: X}
- Failed upload response: [paste]
- Trial status after failed upload: {remaining: X} (unchanged)

## Flow 7b: Stripe Webhook (checkout.session.completed)

### stripe listen output
[paste relevant lines]

### Server response
[paste]

### DB state
[paste transaction query result]

### Verdict: PASS / FAIL
```

## 4. Verification

- [ ] Trial count unchanged after failed upload
- [ ] Stripe webhook receives event (stripe listen shows delivery)
- [ ] Stripe webhook returns 200 (signature verified)
- [ ] No .env.local files committed
- [ ] git status is clean after push

## 5. What This Does NOT Include

- Do NOT fix file extension mismatch
- Do NOT fix service account cross-project
- Do NOT fix Cloud Build pipeline
- Do NOT deploy anywhere

---

**When complete:** Create PR, self-terminate.
