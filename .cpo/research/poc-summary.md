# POC Summary — Honest Image Tools

*Written 2026-03-29 after completing all POC experiments.*

---

## What We Tested

**Core question:** Can Real-ESRGAN run on Google Cloud Run at a viable cost (<$0.05 per image)?

## How We Tested It

### 1. Research Phase (agents, no code)

Two parallel research agents gathered data from the web:

- **Competitive landscape** — Scraped pricing pages and user reviews for 8 competitors (Let's Enhance, Upscale.media, Bigjpg, waifu2x, Topaz Labs, Adobe Enhance, Magnific AI, Upscayl). Results in `.cpo/research/competitive-landscape.md`.
- **Technical feasibility** — Researched Real-ESRGAN model variants, CPU vs GPU inference benchmarks, container requirements, ONNX optimization options, and Cloud Run pricing formulas. Results in `.cpo/research/real-esrgan-feasibility.md`.

These were web-search-only agents (no code execution). They synthesized findings from GitHub issues, documentation, blog posts, and pricing pages.

### 2. Experiment Phase (real code, real Cloud Run)

A supervisor+executor agent pair built and deployed a real service. Here's exactly what ran where:

#### What was built

- **`poc/app.py`** — A 105-line FastAPI service with two endpoints:
  - `POST /upscale` — Accepts an image file upload, runs Real-ESRGAN 4x upscaling, returns the upscaled PNG
  - `GET /health` — Health check for Cloud Run
- **Model used:** `realesr-general-x4v3` (SRVGGNetCompact architecture, ~1.21M parameters, 4.7 MB weight file). This is the **lightweight** model — 14x fewer parameters than the full `RealESRGAN_x4plus`. We chose it because it's the only model viable for CPU-only inference.
- **`poc/Dockerfile`** — Python 3.11-slim base, CPU-only PyTorch, model weights downloaded at build time.

#### Where it ran

1. **Docker build + local test** — Built on the local Mac. Verified a 64x64 test image upscaled to 256x256 in 220ms locally.
2. **Cloud Build** — The Docker image was built in Google Cloud Build (not locally pushed). Command: `gcloud builds submit poc/ --tag us-central1-docker.pkg.dev/photo-upscaler-24h/photo-upscaler/esrgan-poc:latest`
3. **Cloud Run deployment** — Deployed to a real Cloud Run service:
   - **Project:** `photo-upscaler-24h`
   - **Region:** `us-central1`
   - **URL:** `https://esrgan-poc-132808742560.us-central1.run.app`
   - **Config:** 4 vCPU, 8 GiB RAM, CPU-only, concurrency 1, min instances 0 (scale to zero), max instances 1
   - **Auth:** `--allow-unauthenticated` (open for testing)

#### How the benchmarks ran

The benchmark script (`poc/benchmark.sh`) ran **from the executor's local machine, hitting the Cloud Run URL over the internet**. It:

1. Generated 3 synthetic test images using PIL (not photos — patterned color images):
   - Small: 640x480
   - Medium: 1024x768
   - Large: 1920x1080
2. Sent each image 3 times via `curl -X POST -F "file=@image.jpg" $CLOUD_RUN_URL/upscale`
3. Measured two things per request:
   - **Total time** (curl's `time_total`) — includes network round-trip + upload + processing + download
   - **Processing time** (from `X-Processing-Time-Ms` response header) — pure inference time on the server
4. First request was a cold start (container scaled from zero); subsequent requests hit the warm instance.

### Benchmark Results — Raw Data

| Input | Run | Total (s) | Server Processing (ms) | Output | Cold? |
|-------|-----|-----------|----------------------|--------|-------|
| 640x480 | 1 | 13.4 | 11,223 | 2560x1920 | Yes |
| 640x480 | 2 | 11.3 | 10,342 | 2560x1920 | No |
| 640x480 | 3 | 11.1 | 9,185 | 2560x1920 | No |
| 1024x768 | 1 | 31.8 | 28,693 | 4096x3072 | No |
| 1024x768 | 2 | 42.2 | 20,511 | 4096x3072 | No |
| 1024x768 | 3 | 31.3 | 28,810 | 4096x3072 | No |
| 1920x1080 | 1 | 83.8 | 78,012 | 7680x4320 | No |
| 1920x1080 | 2 | 80.5 | 74,601 | 7680x4320 | No |
| 1920x1080 | 3 | 78.3 | 72,631 | 7680x4320 | No |

**Cold start overhead:** ~2-3 seconds (13.4s cold vs ~11.2s warm for the same image).

### Cost Calculation

Cloud Run bills per vCPU-second and GiB-second (us-central1 pricing):
- vCPU: $0.000024/vCPU-second
- Memory: $0.0000025/GiB-second

Formula: `(4 vCPU x seconds x $0.000024) + (8 GiB x seconds x $0.0000025)`

| Input | Avg Processing | vCPU Cost | Memory Cost | **Total/Image** |
|-------|---------------|-----------|-------------|----------------|
| 640x480 | 10.2s | $0.00098 | $0.00020 | **$0.0012** |
| 1024x768 | 26.0s | $0.00250 | $0.00052 | **$0.0030** |
| 1920x1080 | 75.1s | $0.00721 | $0.00150 | **$0.0087** |

All 6-42x under the $0.05 target.

---

## Real Photo Validation (PR #6)

The synthetic benchmark was followed up with 6 real Unsplash photos. **Critical finding: 1920px+ images fail on CPU.**

### Real Photo Results

| Photo | Input | Processing | Cost | Status |
|-------|-------|-----------|------|--------|
| Café scene | 480x320 | 4.3s | $0.0005 | Works |
| Cityscape | 1024x683 | 19.1s | $0.0022 | Works |
| Portrait | 1024x1536 | 46.9s | $0.0054 | Works (slow) |
| Landscape | 1920x1144 | — | — | **HTTP 500 (OOM)** |
| Architecture | 1920x1280 | — | — | **HTTP 500 (OOM)** |
| Nature | 3000x4500 | — | — | **HTTP 504 (timeout)** |

### Key Insight: Processing Scales Linearly

~28μs per input pixel is the consistent rate. This means cost is predictable:
- `cost = (pixels × 28μs) × $0.000116/second`

### Revised Viable Sizes (CPU-only, 4 vCPU, 8 GiB)

| Max Input | Processing | Cost | Viable? |
|-----------|-----------|------|---------|
| ≤640px | <10s | $0.001 | Great |
| ≤1024px | 20-47s | $0.003-0.005 | Acceptable with progress bar |
| 1920px+ | Fails | — | Needs GPU |

### Cost Measurement Approach

GCP provides NO per-request cost data. Recommended approach:
- **MVP:** Formula using `X-Processing-Time-Ms` header: `cost = processing_seconds × $0.000116`
- **Validation:** Cloud Run logs provide per-request latency for weekly reconciliation
- **~95% accurate** vs actual billing (main gap is idle time between requests)

Full details in `poc/real-photo-benchmark.md` and `poc/gcp-cost-measurement.md`.

---

## Caveats & Limitations

1. **1920px+ images fail on CPU.** The synthetic benchmark at 1920x1080 succeeded, but real photos at similar size consistently return HTTP 500 (likely memory exhaustion during 4x upscale). GPU instances are required for large images.

2. **Lightweight model, not the best quality.** We used `realesr-general-x4v3` (~1.21M params) because the full `RealESRGAN_x4plus` (~16.7M params) is impractically slow on CPU. For production, a GPU instance with the full model would give better quality at similar cost.

3. **CPU processing is slow.** 4-47 seconds per image (for viable sizes). Users need a progress indicator. GPU (L4) would bring this to 3-8 seconds.

4. **Large output files.** 1024px input produces 12-25 MB PNG output. Needs compression (WebP/JPEG) before delivery.

5. **Single region tested.** Only `us-central1`.

6. **The service is still live.** The Cloud Run service at `https://esrgan-poc-132808742560.us-central1.run.app` is still deployed (scale-to-zero, so $0 when idle). Should be deleted when no longer needed.

---

## Competitive Context

| Service | Per-Image Cost | Our Cost | Advantage |
|---------|---------------|----------|-----------|
| Let's Enhance | ~$0.09 | $0.003 | 30x cheaper |
| Upscale.media | ~$0.10 | $0.003 | 33x cheaper |
| Magnific AI | ~$0.20 | $0.003 | 67x cheaper |
| Bigjpg | ~$0.006 | $0.003 | 2x cheaper |
| Topaz Labs | ~$0.55/day | $0.003 | 183x cheaper |

**Key differentiator:** Zero competitors show a cost breakdown. We would be the first to display "this image cost $0.002 compute + $0.001 platform fee = $0.003 total."

Full analysis in `.cpo/research/competitive-landscape.md`.

---

## What Comes Next — Lifecycle Stages

The project follows a lifecycle: **POC → Architecture → Beta → Production**.

### Current: POC (DONE)
We've answered the core question. Everything below requires CEO approval at each gate.

### Next: Architecture Stage

*Goal: Design the structure before building on it.*

What happens here:
- **Service design** — How many containers? Monolith (Next.js + FastAPI in one) vs split (frontend + inference API separately)?
- **Data model** — User accounts (magic link), prepaid balance, transaction history, image processing records
- **API contracts** — Define the endpoints between frontend and backend
- **Cost display design** — How exactly do we calculate and show the cost breakdown? Do we measure Cloud Run billing live, or use a formula?
- **Architecture Decision Records (ADRs)** — Document each major choice with reasoning

What we do NOT do here:
- No feature code, no UI beyond wireframes, no auth/payment integration

### Then: Beta Stage

*Goal: Complete v1 feature set at ~80% visual fidelity.*

What gets built:
- **Next.js frontend** — Upload page, processing status, download, cost breakdown display
- **Auth** — Email magic link (simple, no passwords)
- **Payments** — Stripe in sandbox/test mode, prepaid balance model in real currency
- **Full inference API** — Proper FastAPI service (built on POC learnings, but production-quality)
- **GPU upgrade decision** — Run the same benchmarks on L4 GPU, decide CPU vs GPU for production

What we do NOT do here:
- No live payments, no production deployment, no marketing

### Finally: Production Stage

*Goal: Harden, polish, ship.*

What gets built:
- Live Stripe payments (real money)
- Production Cloud Run deployment with real domain
- Security audit, rate limiting, abuse protection
- 100% visual fidelity
- Monitoring and observability
- Legal: terms of service, privacy policy, image deletion policy

### Timeline (from project brief)

| Stage | Original Estimate | Status |
|-------|------------------|--------|
| POC (H1) | 24 hours | **Done in ~1 hour** |
| Beta (H2) | 1 week | Pending CEO approval |
| Production (H3) | 1 month | Pending |

The POC completed much faster than expected. The 24h estimate was conservative.

---

## Files Reference

| File | What it contains |
|------|-----------------|
| `poc/app.py` | FastAPI upscaling service (throwaway POC code) |
| `poc/Dockerfile` | Container definition |
| `poc/benchmark.sh` | Benchmark script |
| `poc/benchmark-results.md` | Raw benchmark data + cost analysis |
| `poc/requirements.txt` | Python dependencies |
| `.cpo/research/competitive-landscape.md` | 8-competitor analysis |
| `.cpo/research/real-esrgan-feasibility.md` | Technical feasibility report |
| `.cpo/lifecycle.md` | Stage tracking + checklists |
