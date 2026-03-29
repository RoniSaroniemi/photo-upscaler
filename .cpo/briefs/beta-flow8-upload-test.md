# Supervisor Brief — Flow 8: Real Upload E2E Test

**Branch:** `fix/flow8-upload`
**Executor session:** `exec-flow8`

## 1. The Problem

Flow 8 (free trial upload → inference → GCS → download) has never been tested against real services. All other flows pass. This is the last Beta gate requirement.

## 2. The Solution

Configure the local dev server to use the real Cloud Run inference service and real GCS bucket, then test the full upload pipeline with a real image. Fix any issues found.

## 3. Implementation

### Phase 1: Environment Setup

1. Copy env from root to frontend:
   ```bash
   cp /Users/roni-saroniemi/Github/photo-upscaler/.env.local /Users/roni-saroniemi/Github/photo-upscaler/frontend/.env.local
   ```

2. Add/update these vars in `frontend/.env.local`:
   ```
   INFERENCE_SERVICE_URL=https://esrgan-poc-132808742560.us-central1.run.app
   GCS_BUCKET_NAME=honest-image-tools-results
   ```

3. Fix GCS IAM — grant the default compute service account objectCreator:
   ```bash
   # Get the project's default service account
   SA=$(gcloud iam service-accounts list --project=photo-upscaler-24h --format="value(email)" --filter="displayName:Compute Engine default" 2>/dev/null | head -1)

   # If that doesn't work, try:
   SA="132808742560-compute@developer.gserviceaccount.com"

   # Grant objectCreator on the bucket
   gsutil iam ch serviceAccount:${SA}:objectCreator gs://honest-image-tools-results/

   # Also ensure local ADC works:
   gcloud auth application-default print-access-token > /dev/null 2>&1 || gcloud auth application-default login
   ```

4. Wake up the inference service (it may be scaled to zero):
   ```bash
   curl -s https://esrgan-poc-132808742560.us-central1.run.app/health
   ```
   If it returns `{"status":"ok"}`, it's alive. If it hangs or times out, wait 30s and retry — cold start.

5. Push DB schema if not already done:
   ```bash
   cd /Users/roni-saroniemi/Github/photo-upscaler/frontend
   source .env.local
   DATABASE_URL="$DATABASE_URL" npx drizzle-kit push
   ```

6. Install deps:
   ```bash
   npm install
   ```

### Phase 2: Test the Upload Pipeline

Start the dev server:
```bash
cd /Users/roni-saroniemi/Github/photo-upscaler/frontend
source .env.local
PORT=3001 npx next dev --port 3001
```

**Test A: API-level upload (curl)**

Use the small test image from POC:
```bash
curl -s -X POST \
  -F "file=@/Users/roni-saroniemi/Github/photo-upscaler/poc/test-images/small-cafe.jpg" \
  http://localhost:3001/api/upscale 2>&1
```

Record the FULL response. Expected: a job object with status, cost breakdown, and download URL.

If it fails, read the error carefully:
- **401 Unauthorized**: the free trial check or auth is blocking. Check proxy.ts exemptions.
- **500 with DB error**: DATABASE_URL not set or schema not pushed.
- **500 with inference error**: INFERENCE_SERVICE_URL wrong or service down.
- **500 with GCS error**: GCS_BUCKET_NAME not set or IAM not configured.
- **500 with other error**: read the server logs in the terminal running `next dev`.

Fix each issue found.

**Test B: Verify the result in GCS**
```bash
gsutil ls gs://honest-image-tools-results/
```
Should show the uploaded result file (e.g., `results/UUID.webp`).

**Test C: Verify the download URL works**
From the job response, extract the `download_url` field and:
```bash
curl -s -o /tmp/downloaded-result.webp "DOWNLOAD_URL_HERE"
file /tmp/downloaded-result.webp
```
Should show: `WebP image data`.

**Test D: Verify cost was calculated**
From the job response, check:
- `compute_cost_microdollars` > 0
- `platform_fee_microdollars` == 5000
- `total_cost_microdollars` == compute + platform
- `processing_time_ms` > 0

**Test E: Verify DB records**
```bash
source .env.local
psql "$DATABASE_URL" -c "SELECT id, status, input_width, input_height, processing_time_ms, compute_cost_microdollars, platform_fee_microdollars, total_cost_microdollars FROM jobs ORDER BY created_at DESC LIMIT 1"
```

If a user was authenticated, also check:
```bash
psql "$DATABASE_URL" -c "SELECT * FROM transactions ORDER BY created_at DESC LIMIT 1"
psql "$DATABASE_URL" -c "SELECT * FROM balances"
```

For free trial, check:
```bash
psql "$DATABASE_URL" -c "SELECT * FROM free_trial_uses"
```

### Phase 3: Evidence Report

Append to `poc/e2e-real-report.md` a new section:

```markdown
## Flow 8: Free Trial Upload — RETESTED

### Environment
- INFERENCE_SERVICE_URL: https://esrgan-poc-132808742560.us-central1.run.app
- GCS_BUCKET_NAME: honest-image-tools-results
- Test image: poc/test-images/small-cafe.jpg (480x320)

### API Response
[paste full JSON response]

### GCS Object
[paste gsutil ls output]

### Downloaded Result
[paste file command output confirming WebP]

### Cost Breakdown
- Compute: $X.XXX (Y microdollars)
- Platform: $0.005 (5000 microdollars)
- Total: $X.XXX (Z microdollars)
- Processing time: Nms

### DB Records
[paste job row]
[paste free_trial_uses row]

### Verdict: PASS / FAIL
```

## 4. Verification

The evidence in the report IS the verification. The following must ALL be true:
- [ ] API returns a job with status "complete" (or progresses from pending to complete)
- [ ] GCS bucket contains the result file
- [ ] Downloaded file is a valid WebP image
- [ ] Cost breakdown has non-zero compute + 5000 platform fee
- [ ] DB has the job record with correct fields
- [ ] Free trial uses table has a record for the IP

## 5. What This Does NOT Include

- No UI testing (just API-level)
- No Stripe payment flow (already tested in Flow 7)
- No deploy to Cloud Run
- No new features

---

**When complete:** Push branch with fixes + updated report, create PR, self-terminate.
