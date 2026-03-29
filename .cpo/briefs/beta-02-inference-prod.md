# Brief — Production Inference Service

**Scope:** Upgrade the POC FastAPI service to production quality with WebP output, input validation, 2x upscale support, and error handling.
**Branch:** `feature/inference-prod` — new worktree
**Effort estimate:** M (< 1 hour)
**Risk:** Low
**Affects:** `inference/` (new directory, production version of poc/), Dockerfile, app.py, requirements.txt
**Project:** PRJ-001 (Honest Image Tools Beta)

---

## 0. Prerequisites (verify before starting)

### Environment
- [ ] Docker installed: `docker --version`
- [ ] Python 3.11+: `python3 --version`
- [ ] gcloud CLI authenticated: `gcloud auth list`

### Credentials & Access
- [ ] GCP project `photo-upscaler-24h` accessible: `gcloud config get-value project`
- [ ] Cloud Run API enabled: already confirmed
- [ ] Artifact Registry API enabled: already confirmed

### Verification Capability
- [ ] Can verify via: `docker build -t inference . && docker run -p 8080:8080 inference`
- [ ] Can test with: `curl -X POST -F "file=@test.jpg" localhost:8080/upscale -o output.webp`
- [ ] Can verify output format: `file output.webp` shows WebP

### Human Dependencies
- [ ] None — fully autonomous (POC exists, Docker + gcloud available)

---

## 1. The Problem (Why)

The POC inference service works but has several gaps for production use:
1. Outputs PNG (12-25 MB) instead of WebP (1-3 MB) — terrible download experience
2. No input validation — 1920px+ images crash the service (HTTP 500)
3. No error handling — any processing failure returns a raw exception
4. Only supports 4x upscale — BL-002 requests 2x option
5. Uses deprecated FastAPI `on_event` startup

---

## 2. The Solution (What)

### 2.1 WebP Output Conversion

Replace PNG encoding with WebP at quality 90:
```python
# Instead of: cv2.imencode(".png", output)
# Use: PIL Image + WebP encoding
from PIL import Image
img_pil = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
buffer = io.BytesIO()
img_pil.save(buffer, format="WEBP", quality=90)
```

Return `media_type="image/webp"` in the response.

### 2.2 Input Validation

- Validate image dimensions before processing
- Reject images with longest side > 1024px (return 400 with clear message)
- Reject files > 10 MB
- Reject non-image files (validate MIME type and actual image decode)

### 2.3 2x Upscale Support (BL-002)

The `realesr-general-x4v3` model supports `outscale` parameter of 2 or 4. The `scale` query param already exists in the POC. Ensure:
- `scale=2` passes `outscale=2` to `upsampler.enhance()`
- `scale=4` is the default
- Response headers reflect actual output dimensions

### 2.4 Error Handling

- Wrap `upsampler.enhance()` in try/except
- Return 500 with JSON error body on processing failure (not raw traceback)
- Add request timeout: if processing exceeds 90 seconds, abort and return 504
- Log processing metrics (input size, processing time, output size) to stdout

### 2.5 Health + Estimate Endpoints

- `GET /health` — returns model loaded status, version
- `GET /estimate?width=W&height=H` — returns estimated processing seconds and cost using the formula: `seconds = (W * H * 28) / 1_000_000`

### 2.6 Production Dockerfile

- Pin all dependency versions
- Multi-stage build for smaller image
- Download model at build time (already done in POC)
- Use `lifespan` context manager instead of deprecated `on_event`
- Set `--timeout-keep-alive 120` in uvicorn

---

## 3. Design Alignment

Implements ADR-001 (inference as separate service), ADR-005 (WebP output, 1024px cap), and addresses BL-002 (2x upscale option from backlog).

---

## 3.5 Lifecycle Stage & Scope Lock

**Current stage:** Architecture

**Stage-appropriate work in this brief:**
- Upgrading POC to production-quality service (Architecture → Beta transition)
- This is infrastructure, not feature code

**Out of scope for this stage:**
- GPU support (Production stage, BL-001)
- New ML models
- Tiled processing for large images

---

## 4. Implementation Plan

### Phase 1: Copy + Upgrade
- Create `inference/` directory (production version, separate from `poc/`)
- Copy and upgrade `app.py` with WebP conversion, input validation, error handling
- Update `requirements.txt` with pinned versions
- Update `Dockerfile` with multi-stage build

### Phase 2: Test Locally
- `docker build -t inference-prod .`
- `docker run -p 8080:8080 inference-prod`
- Test with various images: small (480x320), medium (1024x768), oversized (2000x1500)
- Verify WebP output, 2x scale, error responses, health endpoint

### Phase 3: Deploy to Cloud Run
- `gcloud builds submit --tag gcr.io/photo-upscaler-24h/inference`
- `gcloud run deploy inference --image gcr.io/photo-upscaler-24h/inference --platform managed --region us-central1 --cpu 4 --memory 8Gi --concurrency 1 --timeout 120 --no-allow-unauthenticated`
- Note: `--no-allow-unauthenticated` — only the frontend service account can call this

---

## 6. Verification & Evidence

### Tests
| Test | What It Verifies |
|------|-----------------|
| POST /upscale with 480x320 JPEG → WebP response | WebP conversion works |
| POST /upscale with 1024x768 JPEG, scale=2 → 2048x1536 output | 2x upscale works |
| POST /upscale with 2000px image → 400 error | Input validation rejects oversized |
| POST /upscale with non-image file → 400 error | MIME validation works |
| POST /upscale with 15 MB file → 413 error | File size limit enforced |
| GET /health → 200 with model status | Health check works |
| GET /estimate?width=1024&height=768 → estimated seconds | Estimate endpoint works |
| Response headers contain X-Processing-Time-Ms | Timing metadata present |

### Acceptance Criteria
- [ ] Output is WebP format, < 3 MB for 1024px input
- [ ] Images > 1024px longest side are rejected with clear error
- [ ] scale=2 and scale=4 both work correctly
- [ ] Processing errors return JSON error, not stack trace
- [ ] Health endpoint returns model status
- [ ] Estimate endpoint returns correct estimates
- [ ] Docker image builds and runs successfully
- [ ] Service deployed to Cloud Run with --no-allow-unauthenticated

---

## 7. What This Does NOT Include

- Frontend integration (Brief 5)
- GCS upload (handled by Next.js API route in Brief 5)
- GPU support (BL-001, Production stage)
- Authentication/authorization (handled by Cloud Run IAM)
- Cost calculation business logic (handled by Next.js in Brief 5)

---

## 8. Challenge Points

- [ ] **WebP quality 90 file sizes:** Assume WebP q90 reduces 25 MB PNG to ~2-3 MB. Verify with actual benchmark images. If still too large, reduce quality to 85.
- [ ] **2x upscale with general-x4v3 model:** Assume the model supports outscale=2 natively. Verify — some Real-ESRGAN models only support their trained scale factor and need post-resize for other scales.
- [ ] **Cloud Run timeout interaction:** Assume 120s Cloud Run timeout is enough for 1024x1536 images (~47s processing). The current 300s default works but 120s is tighter. Verify with worst-case input.

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| WebP encoding slower than PNG | Adds processing time | Benchmark; PIL WebP encoding is typically fast (~100ms) |
| Model doesn't support outscale=2 | BL-002 blocked | Test locally first; fallback: upscale 4x then downscale 2x |
| Docker image too large (>2 GB) | Slow Cloud Run cold starts | Multi-stage build, CPU-only torch wheels |

---

## Convention: PR-Based Completion

**Supervisors create PRs on completion — they do NOT merge directly.** When all work is done and verified, the supervisor must:
1. `git push origin feature/inference-prod`
2. `gh pr create --title "PRJ-001: Production inference service with WebP + 2x" --body "..." --base main --head feature/inference-prod`
3. State "WORK COMPLETE — PR created, ready for review"

---

## Convention: Autonomy Bias

**Fully autonomous.** No human interaction needed. Docker + gcloud are available.

---

*Brief version: 1.0 — 2026-03-29*
