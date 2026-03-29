# Brief — Upload Flow + Core API

**Scope:** Implement the complete image upload, inference proxy, job management, cost calculation, and GCS storage pipeline.
**Branch:** `feature/upload-flow` — new worktree
**Effort estimate:** XL (~4 hours)
**Risk:** High (integration of 4 subsystems: inference, auth, payments, storage)
**Affects:** `frontend/src/app/api/upscale/`, `frontend/src/app/api/pricing/`, `frontend/src/lib/`, GCS bucket setup
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Node.js >= 20: `node --version`
- [ ] gcloud CLI authenticated: `gcloud auth list`

### Credentials & Access
- [ ] Brief 1 (Foundation) merged: database schema + Drizzle ORM working
- [ ] Brief 2 (Inference) merged: production inference service deployed to Cloud Run
- [ ] Brief 3 (Auth) merged: auth middleware working, session cookies functional
- [ ] Brief 4 (Payments) merged: `deductBalance()` function available
- [ ] Inference service URL in `.env.local`: `INFERENCE_SERVICE_URL=https://inference-xxx.run.app`
- [ ] GCS credentials: Application Default Credentials via `gcloud auth application-default login` or service account key
- [ ] `GCS_BUCKET_NAME` in `.env.local`

### Verification Capability
- [ ] Can verify via: `npm run dev` → upload an image → verify job completes
- [ ] Can verify GCS: `gsutil ls gs://$GCS_BUCKET_NAME`
- [ ] Can verify signed URL: download result via the returned URL

### Human Dependencies
- [ ] GCS bucket creation — agent can create via `gsutil mb gs://honest-image-tools-uploads -l us-central1`
- [ ] Service account for Cloud Run IAM (if not using default compute SA)

---

## 1. The Problem (Why)

This is the core product flow: user uploads an image, it gets upscaled, they see the cost breakdown and download the result. It connects all the subsystems built in Briefs 1-4: authentication (who is this user?), balance (can they afford this?), inference (process the image), storage (deliver the result), and the cost calculation engine that makes the product unique.

---

## 2. The Solution (What)

### 2.1 Pricing Estimate API

**GET /api/pricing/estimate?width=W&height=H** (no auth required)

Calculate estimated cost using the formula from the architecture doc:
```
processing_seconds = (width * height * 28) / 1_000_000  // 28μs per input pixel
compute_cost_microdollars = Math.round(processing_seconds * 116)  // $0.000116/s = 116 microdollars/s
platform_fee_microdollars = 5000  // flat $0.005
total_microdollars = compute_cost_microdollars + platform_fee_microdollars
```

Response:
```json
{
  "input_pixels": 786432,
  "estimated_processing_seconds": 22.0,
  "cost_breakdown": {
    "compute_microdollars": 2552,
    "platform_fee_microdollars": 5000,
    "total_microdollars": 7552
  },
  "formatted_total": "$0.008",
  "max_input_px": 1024
}
```

Reject if width or height > 1024 (return 400).

**GET /api/pricing/formula** (no auth required)

Return the current pricing constants for the pricing page.

### 2.2 Image Upload + Upscale API

**POST /api/upscale** (auth required)

Request: `multipart/form-data` with `file` field and optional `scale` param (2 or 4, default 4).

Flow (matching the architecture data flow diagram):
1. **Validate input:**
   - Check file is an image (MIME type check)
   - Check file size <= 10 MB
   - Read image dimensions (use `sharp` or read EXIF/header)
   - Reject if longest side > 1024px
2. **Estimate cost:**
   - Calculate estimated cost using the pricing formula
3. **Check balance:**
   - Query user's balance
   - If balance < estimated cost → return 402 with balance and required amounts
4. **Create job record:**
   - INSERT into `jobs` table: status="pending", dimensions, estimated cost
5. **Proxy to inference service:**
   - Forward the image to the inference Cloud Run service via `POST /upscale`
   - Use Cloud Run IAM for service-to-service auth (get ID token from metadata server or `google-auth-library`)
   - Set appropriate timeout (120s)
   - Stream the request, await the response
6. **On success:**
   - Read `X-Processing-Time-Ms` from inference response headers
   - Calculate ACTUAL cost from real processing time (not estimate)
   - Upload WebP result to GCS with random UUID key and 24h lifecycle
   - Generate signed URL with 1-hour expiry
   - **Atomic deduction:** Use `deductBalance()` with the ACTUAL cost
   - UPDATE job: status="complete", actual dimensions, processing time, cost breakdown, GCS key
   - Return job response with download URL and cost breakdown
7. **On failure:**
   - UPDATE job: status="failed", error message
   - **No charge** — balance is NOT deducted for failed jobs
   - Return job response with error

Return: `{ job_id, status: "pending", estimated_cost: {...}, estimated_seconds }`

**Important design decision:** The upload API is synchronous from the client's perspective during Beta. The request stays open until processing completes (10-47s). This is simpler than async with polling for MVP. If the connection drops, the job still completes server-side and the user can retrieve it via the jobs endpoint.

Alternative considered: async job submission + polling. This is the architecture's original design. Implement this if the synchronous approach causes issues with Cloud Run timeout or client disconnection. The job table supports both patterns.

### 2.3 Job Status API

**GET /api/upscale/jobs/:id** (auth required)
- Return job record (verify user owns this job)
- If status="complete" and download_url expired, generate a new signed URL (if within 24h of completion)
- If status="complete" and > 24h, return job record without download URL

**GET /api/upscale/jobs** (auth required)
- List user's jobs, ordered by created_at DESC
- Pagination: `?limit=10&offset=0`
- Include cost breakdown on completed jobs

### 2.4 GCS Integration

Setup:
- `npm install @google-cloud/storage`
- Create bucket with 24h lifecycle policy:
  ```bash
  gsutil mb -l us-central1 gs://honest-image-tools-uploads
  gsutil lifecycle set lifecycle.json gs://honest-image-tools-uploads
  ```
  Where `lifecycle.json`:
  ```json
  { "rule": [{ "action": { "type": "Delete" }, "condition": { "age": 1 } }] }
  ```

Upload:
- Key format: `results/{uuid}.webp`
- Content-Type: `image/webp`
- No public access (signed URLs only)

Signed URL:
- Generate V4 signed URL with 1-hour expiry
- Include in job response

### 2.5 Service-to-Service Auth

The Next.js service needs to call the inference Cloud Run service, which has `--no-allow-unauthenticated`.

Use `google-auth-library` to get an ID token:
```typescript
import { GoogleAuth } from 'google-auth-library';
const auth = new GoogleAuth();
const client = await auth.getIdTokenClient(INFERENCE_SERVICE_URL);
const headers = await client.getRequestHeaders();
// Include headers.Authorization in the fetch to inference service
```

This works automatically on Cloud Run (uses the service's identity). For local dev, requires `gcloud auth application-default login`.

### 2.6 Cost Calculation Module

Create `src/lib/pricing/cost.ts`:
```typescript
const PIXEL_RATE_US = 28;  // microseconds per input pixel
const COMPUTE_RATE_MICRODOLLARS_PER_S = 116;  // $0.000116/s
const PLATFORM_FEE_MICRODOLLARS = 5000;  // $0.005

function estimateCost(width: number, height: number): CostBreakdown
function calculateActualCost(processingTimeMs: number): CostBreakdown
```

Both functions return:
```typescript
interface CostBreakdown {
  compute_microdollars: number;
  platform_fee_microdollars: number;
  total_microdollars: number;
  processing_seconds: number;
}
```

---

## 3. Design Alignment

This is the integration brief — it connects ADR-001 (hybrid architecture), ADR-003 (API design), ADR-004 (cost display), and ADR-005 (image handling). The cost calculation module is the heart of the product's value proposition.

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Beta

**Stage-appropriate work in this brief:**
- Full upload flow is a Beta deliverable
- GCS integration is a Beta deliverable

**Out of scope for this stage:**
- GPU routing (Production stage)
- Batch uploads
- Image resize-before-upscale (deferred)
- Background job queue (sync approach for Beta)

---

## 4. Implementation Plan

### Phase 1: Cost Calculation + Pricing API
- Create `src/lib/pricing/cost.ts` with estimate and actual cost functions
- Create `GET /api/pricing/estimate` route
- Create `GET /api/pricing/formula` route
- Test: verify estimates match benchmark data

### Phase 2: GCS Setup
- Create GCS bucket with lifecycle policy
- Create `src/lib/storage/gcs.ts` — upload, generate signed URL
- Test: upload a test file, generate signed URL, download it

### Phase 3: Inference Proxy
- Create `src/lib/inference/client.ts` — service-to-service auth, proxy to inference
- Test: send a test image, receive WebP response with timing headers

### Phase 4: Upload API Integration
- Create `POST /api/upscale` — the full flow
- Create `GET /api/upscale/jobs/:id`
- Create `GET /api/upscale/jobs`
- Test: full upload → process → download flow

### Phase 5: Integration Testing
- Test with small image (480x320) — fast, cheap
- Test with medium image (1024x768) — verify timing and cost
- Test insufficient balance → 402
- Test oversized image → 400
- Test inference failure → job marked failed, no charge

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| GET /api/pricing/estimate?width=1024&height=768 → correct estimate | Cost calculation works |
| GET /api/pricing/estimate?width=2000&height=1500 → 400 | Oversized rejection works |
| POST /api/upscale with 480x320 image → complete with WebP download | Full pipeline works |
| POST /api/upscale with 1024x768 → cost breakdown matches estimate (~$0.008) | Actual vs estimate alignment |
| POST /api/upscale with insufficient balance → 402 | Balance check works |
| POST /api/upscale with > 1024px → 400 | Input validation works |
| POST /api/upscale with > 10 MB → 413 | File size limit works |
| GET /api/upscale/jobs/:id → complete job with signed URL | Job retrieval works |
| Signed URL downloads the WebP file | GCS signed URLs work |
| Failed inference → job status "failed", no balance deduction | Error handling works |

### Acceptance Criteria
- [ ] Complete upload → upscale → download flow works end-to-end
- [ ] Cost is calculated from actual processing time (not just estimate)
- [ ] Cost breakdown shows compute + platform fee in microdollars
- [ ] Balance is only deducted on successful processing
- [ ] Failed jobs incur no charge
- [ ] Results stored in GCS with 24h auto-deletion
- [ ] Signed URLs expire after 1 hour
- [ ] Service-to-service auth works (inference is not publicly accessible)
- [ ] Input validation: max 1024px, max 10 MB, image files only

---

## 7. What This Does NOT Include

- Frontend upload UI (Brief 6)
- Free trial flow (Brief 6)
- Polling/progress UI (Brief 6)
- Batch uploads
- Image resize before upscale
- Retry logic for transient inference failures
- Job cancellation

---

## 8. Challenge Points

- [ ] **Synchronous vs async upload:** The brief proposes keeping the HTTP request open for 10-47s. Verify that Next.js API routes + Cloud Run support this without timeout. If Cloud Run has a 60s timeout on the frontend service, the 47s max processing time leaves only 13s for overhead. Consider increasing frontend Cloud Run timeout to 120s or switching to async with polling.
- [ ] **Service-to-service auth in local dev:** `google-auth-library` needs Application Default Credentials locally. Verify `gcloud auth application-default login` is sufficient, or provide a fallback (e.g., skip auth in dev mode with the inference service running locally via Docker).
- [ ] **Cost estimate vs actual cost divergence:** The estimate uses 28μs/pixel but actual processing varies. If actual cost is >20% higher than estimate, the user may be surprised. Consider: charge the LOWER of estimate and actual, absorbing the difference as a goodwill gesture.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Next.js API route timeout | Upload fails on large images | Set Cloud Run timeout to 120s; switch to async if needed |
| GCS upload fails | User processed but can't download | Return image directly in response as fallback |
| Inference service cold start | First request takes 30-60s | Accept for Beta; add minimum instances in Production |
| Cost estimate wildly wrong | User trust eroded | Log estimate vs actual; tune formula with real data |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/upload-flow`
2. `gh pr create --title "PRJ-001: Upload flow + cost engine + GCS storage" --body "..." --base main --head feature/upload-flow`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Fully autonomous.** All dependencies (Briefs 1-4) are merged. GCS bucket can be created by agent. No human interaction needed.

---

*Brief version: 1.0 — 2026-03-29*
