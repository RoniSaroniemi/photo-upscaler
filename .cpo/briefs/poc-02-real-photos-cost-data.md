# Supervisor Brief — POC: Real Photo Validation + GCP Cost Measurement

**Branch:** `poc/real-photo-validation`
**Executor session:** `exec-poc02`

## 1. The Problem

Our POC benchmark used synthetic test images (generated with PIL). Real photographs have more complex textures and detail, which could mean significantly different processing times. We need to validate that our cost estimates hold with real images.

Additionally, our cost calculation used a formula (vCPU-seconds x rate). For the actual product, we need to know: how do we get real cost data from GCP so we can show users accurate cost breakdowns?

## 2. The Solution

Two quick experiments:

**Experiment A:** Run the existing Cloud Run service with 5-6 real photographs at varying sizes and measure processing times. Compare to synthetic benchmark.

**Experiment B:** Research and test GCP methods for getting per-request cost data (Cloud Monitoring metrics, billing export, or Cloud Run metrics API).

## 3. Implementation Phases

### Phase 1: Get Real Test Photos

1. Download 5-6 Creative Commons / public domain photos from the web. Use `curl` or `wget` to download from sources like:
   - Unsplash API (free photos): `https://unsplash.com/photos/<id>/download` or search for direct image URLs
   - Wikimedia Commons
   - Pexels

   Get a variety:
   - 1 small photo (~640x480 or similar)
   - 2 medium photos (~1024x768 range)
   - 2 large photos (~1920x1080 range)
   - 1 very large photo (~3000x2000+ if possible, to test limits)

2. Save them in `poc/test-images/` with descriptive names (e.g., `landscape-1920x1080.jpg`, `portrait-640x480.jpg`)
3. Record actual dimensions and file sizes

### Phase 2: Benchmark with Real Photos

1. The Cloud Run service should still be live at: `https://esrgan-poc-132808742560.us-central1.run.app`
   - First verify it responds: `curl -s https://esrgan-poc-132808742560.us-central1.run.app/health`
   - If down, it may need a cold start — retry after 30 seconds

2. For each test photo, run 2 requests (1 cold/warm, 1 warm):
   ```bash
   curl -s -w "\nHTTP %{http_code}, Total: %{time_total}s" \
     -X POST -F "file=@poc/test-images/<photo>.jpg" \
     -D /tmp/headers.txt \
     "https://esrgan-poc-132808742560.us-central1.run.app/upscale" \
     --output /tmp/upscaled-<photo>.png

   # Read processing time from header
   grep -i 'x-processing-time-ms' /tmp/headers.txt
   ```

3. Write results to `poc/real-photo-benchmark.md`:
   - Table: photo name, input dimensions, file size, processing time, output dimensions
   - Compare with synthetic benchmarks: are real photos significantly slower?
   - Updated cost estimates based on real photo processing times

### Phase 3: GCP Cost Measurement Research

Research and test how to get actual per-request cost data. Try these approaches:

1. **Cloud Run Metrics (Cloud Monitoring API)**
   ```bash
   # Check what metrics are available for the service
   gcloud monitoring metrics list --filter="metric.type=starts_with(\"run.googleapis.com\")" --project=photo-upscaler-24h 2>&1 | head -30

   # Get request count and latency metrics
   gcloud monitoring read \
     "run.googleapis.com/request_count" \
     --project=photo-upscaler-24h \
     --start-time=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) 2>&1

   # Get container CPU and memory usage
   gcloud monitoring read \
     "run.googleapis.com/container/cpu/utilization" \
     --project=photo-upscaler-24h \
     --start-time=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) 2>&1
   ```

2. **Cloud Run Instance Time (billable time)**
   ```bash
   # Check if billable instance time metric exists
   gcloud monitoring read \
     "run.googleapis.com/container/billable_instance_time" \
     --project=photo-upscaler-24h \
     --start-time=$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) 2>&1
   ```

3. **Cloud Billing Export**
   ```bash
   # Check if billing export is configured
   gcloud billing accounts list --project=photo-upscaler-24h 2>&1

   # Check BigQuery billing export (if configured)
   bq ls --project_id=photo-upscaler-24h 2>&1
   ```

4. **Cloud Run Logs (request-level data)**
   ```bash
   # Get Cloud Run request logs with timing
   gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=esrgan-poc" \
     --project=photo-upscaler-24h \
     --limit=10 \
     --format=json 2>&1 | python3 -c "
   import json,sys
   logs = json.load(sys.stdin)
   for log in logs:
     http = log.get('httpRequest', {})
     print(f\"  Status: {http.get('status')}, Latency: {http.get('latency')}, Size: {http.get('responseSize')} bytes\")
   "
   ```

5. Write findings to `poc/gcp-cost-measurement.md`:
   - Which GCP APIs/tools give us per-request cost data?
   - Can we get billable vCPU-seconds and GiB-seconds per request?
   - What's the most practical way to calculate and display cost per image in real time?
   - Recommendation: formula-based (using our own timing) vs GCP metrics vs billing export

## 4. Verification

```bash
# Test photos downloaded
ls -la poc/test-images/

# Real photo benchmark completed
cat poc/real-photo-benchmark.md

# GCP cost measurement research completed
cat poc/gcp-cost-measurement.md
```

## 5. What This Does NOT Include

- No code changes to the service
- No new deployments
- No auth, frontend, or payment work
- No architecture decisions — this is purely validation

---

## 6. Lifecycle Stage & Scope Lock

**Current lifecycle stage:** POC (final validation before Architecture)

**Allowed at this stage:** Research, experiments, benchmarks

**NOT allowed at this stage:** Production code, auth, payments, polished UI

**Scope lock:** This is a quick validation experiment. Do NOT expand scope into building new services or features.

---

## If Your Executor Stalls

Kill and replace: `tmux -L photo-upscaler kill-session -t exec-poc02`

---

**IMPORTANT: When all phases are complete:**

1. Push your branch and create a PR
2. Final message: **WORK COMPLETE — PR created, ready for review**
3. Self-terminate
