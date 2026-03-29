# Supervisor Brief — POC: Real-ESRGAN Container + Cloud Run Benchmark

**Branch:** `poc/esrgan-container`
**Executor session:** `exec-poc01`

## 1. The Problem

We need to validate whether Real-ESRGAN can run on Google Cloud Run at a viable cost (<$0.05/image). This is the core POC experiment for Honest Image Tools. No code exists yet — we need to build a minimal containerized inference service, deploy it, and measure real-world cost and performance.

## 2. The Solution

Build a throwaway FastAPI service that accepts an image upload, runs Real-ESRGAN upscaling, and returns the upscaled image. Containerize it, deploy to Cloud Run in the `photo-upscaler-24h` GCP project, and benchmark with test images at various resolutions.

**Key decisions:**
- Start with `realesr-general-x4v3` (lightweight SRVGGNetCompact model, ~1.21M params, 4.7 MB)
- CPU-only container (no GPU for POC — cheaper, simpler)
- 4 vCPU, 8 GiB RAM Cloud Run configuration
- FastAPI with a single `/upscale` POST endpoint
- No auth, no frontend, no database — pure inference POC

## 3. Implementation Phases

### Phase 1: FastAPI Inference Service

1. Create `poc/` directory at project root for all POC code
2. Create `poc/app.py` — FastAPI application with:
   - `POST /upscale` — accepts multipart image upload, returns upscaled image as PNG
   - `GET /health` — returns `{"status": "ok"}` for Cloud Run health checks
   - On startup: load the `realesr-general-x4v3` model into memory
   - Use `realesrgan` Python package with `RealESRGANer` class
   - Set tile size to 256 for memory management
   - Accept optional query param `scale` (2 or 4, default 4)
   - Return response headers with processing time (`X-Processing-Time-Ms`)
3. Create `poc/requirements.txt`:
   ```
   fastapi>=0.104.0
   uvicorn[standard]>=0.24.0
   python-multipart>=0.0.6
   torch>=2.1.0 --index-url https://download.pytorch.org/whl/cpu
   torchvision>=0.16.0 --index-url https://download.pytorch.org/whl/cpu
   realesrgan>=0.3.0
   basicsr>=1.4.2
   facexlib>=0.3.0
   gfpgan>=1.3.8
   numpy>=1.24.0
   opencv-python-headless>=4.8.0
   Pillow>=10.0.0
   ```
4. Test locally: `cd poc && pip install -r requirements.txt && uvicorn app:app --host 0.0.0.0 --port 8080`
5. Test with curl: `curl -X POST -F "file=@test.jpg" http://localhost:8080/upscale --output upscaled.png`

### Phase 2: Containerize

1. Create `poc/Dockerfile`:
   ```dockerfile
   FROM python:3.11-slim

   WORKDIR /app

   # Install system deps for opencv
   RUN apt-get update && apt-get install -y --no-install-recommends \
       libgl1-mesa-glx libglib2.0-0 && \
       rm -rf /var/lib/apt/lists/*

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Download model weights at build time
   RUN python -c "from realesrgan import RealESRGANer; from basicsr.archs.rrdbnet_arch import RRDBNet; from realesrgan.archs.srvgg_arch import SRVGGNetCompact; import torch; model = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type='prelu'); from huggingface_hub import hf_hub_download; print('Model architecture ready')" || echo "Will download at runtime"

   COPY app.py .

   EXPOSE 8080
   CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
   ```
   Note: The model weights for realesr-general-x4v3 should be downloaded during build or on first startup. Check the Real-ESRGAN documentation for the correct download method. The weights are at: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
2. Build locally: `docker build -t esrgan-poc poc/`
3. Test locally: `docker run -p 8080:8080 esrgan-poc` and repeat curl test

### Phase 3: Deploy to Cloud Run & Benchmark

1. Deploy to Cloud Run using the `photo-upscaler-24h` GCP project:
   ```bash
   # Build and push to Artifact Registry
   gcloud auth configure-docker us-central1-docker.pkg.dev

   # Create Artifact Registry repo if needed
   gcloud artifacts repositories create photo-upscaler \
     --repository-format=docker \
     --location=us-central1 \
     --project=photo-upscaler-24h 2>/dev/null || true

   # Build with Cloud Build (avoids local Docker issues)
   gcloud builds submit poc/ \
     --tag us-central1-docker.pkg.dev/photo-upscaler-24h/photo-upscaler/esrgan-poc:latest \
     --project=photo-upscaler-24h

   # Deploy to Cloud Run
   gcloud run deploy esrgan-poc \
     --image us-central1-docker.pkg.dev/photo-upscaler-24h/photo-upscaler/esrgan-poc:latest \
     --platform managed \
     --region us-central1 \
     --memory 8Gi \
     --cpu 4 \
     --timeout 300 \
     --concurrency 1 \
     --min-instances 0 \
     --max-instances 1 \
     --allow-unauthenticated \
     --project photo-upscaler-24h
   ```
2. Get the Cloud Run URL from the deploy output
3. Benchmark with test images. Create `poc/benchmark.sh`:
   - Download 3 test images: small (640x480), medium (1024x768), large (1920x1080)
   - Use `curl` with timing to measure cold start + inference
   - Run each size 3 times (1 cold, 2 warm)
   - Record: total time, processing time (from X-Processing-Time-Ms header), image sizes
   - Save results to `poc/benchmark-results.md`

4. Write `poc/benchmark-results.md` with:
   - Cold start time
   - Warm inference time per image size
   - Output image quality (file sizes, resolution)
   - Estimated cost per image (using Cloud Run pricing formula)
   - GO/NO-GO recommendation

## 4. Verification

```bash
# 1. Local service runs
cd poc && uvicorn app:app --host 0.0.0.0 --port 8080 &
curl -s http://localhost:8080/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'; print('Health: OK')"

# 2. Upscaling works locally
curl -X POST -F "file=@test.jpg" http://localhost:8080/upscale --output upscaled.png -w "\nHTTP %{http_code}, Time: %{time_total}s\n"
python3 -c "from PIL import Image; img=Image.open('upscaled.png'); print(f'Output: {img.size[0]}x{img.size[1]}')"

# 3. Docker build succeeds
docker build -t esrgan-poc poc/

# 4. Cloud Run deployment succeeds
gcloud run services describe esrgan-poc --region us-central1 --project photo-upscaler-24h --format="value(status.url)"

# 5. Cloud Run inference works
CLOUD_RUN_URL=$(gcloud run services describe esrgan-poc --region us-central1 --project photo-upscaler-24h --format="value(status.url)")
curl -X POST -F "file=@test.jpg" "$CLOUD_RUN_URL/upscale" --output cloud-upscaled.png -w "\nHTTP %{http_code}, Time: %{time_total}s\n"

# 6. Benchmark results documented
cat poc/benchmark-results.md
```

## 5. What This Does NOT Include

- No frontend or UI
- No authentication or user management
- No Stripe/payment integration
- No database or image storage (images are processed and returned, not persisted)
- No production-quality error handling
- No GPU support (CPU-only for this POC)
- No domain name or SSL setup
- No monitoring or logging beyond default Cloud Run
- Do NOT refactor or clean up the POC code — it is throwaway
- Do NOT optimize the Docker image size — just make it work
- Do NOT test with the RealESRGAN_x4plus model — only realesr-general-x4v3

---

## 6. Lifecycle Stage & Scope Lock

**Current lifecycle stage:** POC

**Allowed at this stage:** Research, experiments, throwaway prototypes, cost benchmarks

**NOT allowed at this stage:** Production code, auth, payments, deployment, polished UI

**Scope lock:** This brief covers ONLY work appropriate for the POC stage — a throwaway experiment to validate feasibility. If during execution you discover work that belongs to a later stage (e.g., "we should add auth" or "let's make the UI nice"), note it but do NOT implement it.

---

## If Your Executor Stalls

If the executor repeats the same actions for 10+ minutes without progress:
- Kill the executor: `tmux -L photo-upscaler kill-session -t exec-poc01`
- Create a fresh executor session and relaunch
- Re-send only the remaining work, not the full brief

---

**IMPORTANT: When all phases are complete and all verification passes:**

1. Push your branch and create a PR
2. Your final message must be: **WORK COMPLETE — PR created, ready for review**
3. Self-terminate
