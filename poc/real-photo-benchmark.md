# Real Photo Benchmark Results

## Test Setup
- Model: realesr-general-x4v3 (SRVGGNetCompact, ~1.21M params)
- Scale: 4x
- Cloud Run config: 4 vCPU, 8 GiB RAM, CPU-only
- Concurrency: 1
- Service URL: https://esrgan-poc-132808742560.us-central1.run.app
- Date: 2026-03-29
- Source: Unsplash Creative Commons photos (real-world content)

## Test Photos

| Photo | Subject | Input Dimensions | File Size |
|-------|---------|-----------------|-----------|
| small-cafe.jpg | Street/café scene | 480x320 | 38 KB |
| medium-cityscape.jpg | City skyline | 1024x683 | 150 KB |
| medium-portrait.jpg | Human portrait | 1024x1536 | 315 KB |
| large-landscape.jpg | Forest landscape | 1920x1144 | 381 KB |
| large-architecture.jpg | Building exterior | 1920x1280 | 476 KB |
| xlarge-nature.jpg | Waterfall/nature | 3000x4500 | 3,590 KB |

## Results

| Photo | Input | Run | HTTP | Total Time (s) | Processing Time (ms) | Output Dimensions | Output Size |
|-------|-------|-----|------|----------------|---------------------|-------------------|-------------|
| small-cafe.jpg | 480x320 | 1 | 200 | 5.84 | 4,196 | 1920x1280 | 3.0 MB |
| small-cafe.jpg | 480x320 | 2 | 200 | 5.89 | 4,388 | 1920x1280 | 3.0 MB |
| medium-cityscape.jpg | 1024x683 | 1 | 200 | 22.84 | 19,477 | 4096x2732 | 12.6 MB |
| medium-cityscape.jpg | 1024x683 | 2 | 200 | 21.66 | 18,628 | 4096x2732 | 12.6 MB |
| medium-portrait.jpg | 1024x1536 | 1 | 200 | 50.34 | 45,280 | 4096x6144 | 24.8 MB |
| medium-portrait.jpg | 1024x1536 | 2 | 200 | 53.67 | 48,559 | 4096x6144 | 24.8 MB |
| large-landscape.jpg | 1920x1144 | 1 | **500** | 68.33 | — | — | — |
| large-landscape.jpg | 1920x1144 | 2 | **500** | 72.77 | — | — | — |
| large-architecture.jpg | 1920x1280 | 1 | **500** | 71.27 | — | — | — |
| xlarge-nature.jpg | 3000x4500 | 1 | **504** | 302.05 | — | — | — |

## Comparison with Synthetic Benchmarks

| Metric | Synthetic (benchmark.sh) | Real Photos | Delta |
|--------|------------------------|-------------|-------|
| 480–640px processing | ~10.2s | ~4.3s | **2.4x faster** |
| 1024px processing | ~26.0s (768px square) | 19.1s (683px) / 46.9s (1536px) | Depends on pixel count |
| 1920px processing | ~75.1s (succeeded) | **500 error** (failed) | **Service crash** |

### Key Observations

1. **Real photos process faster than synthetic at small sizes.** 480x320 real photo: ~4.3s vs 640x480 synthetic: ~10.2s. The difference is mainly due to fewer total pixels (153K vs 307K).

2. **Processing time scales linearly with pixel count**, not dimensions:
   - 480x320 = 153,600 px → ~4.3s (~28μs/px)
   - 1024x683 = 699,392 px → ~19.1s (~27μs/px)
   - 1024x1536 = 1,572,864 px → ~46.9s (~30μs/px)
   - **~28μs per input pixel** is the consistent CPU throughput rate

3. **1920px+ images crash the service.** The synthetic benchmark reported 75s success at 1920x1080, but real-world tests consistently return HTTP 500 after ~68-72s. This may indicate:
   - Cloud Run request timeout (default 300s, but could be lower)
   - Memory exhaustion during 4x upscale of 1920px images (output would be 7680px)
   - The synthetic test may have run on a warmer/different instance

4. **3000px+ images gateway-timeout (504).** The 3000x4500 image (13.5M pixels) would take ~6+ minutes on CPU — far exceeding any reasonable timeout.

5. **Output files are very large.** A 1024px input produces 12-25 MB PNG output. Needs compression or format conversion before delivery.

## Updated Cost Estimates (Real Photos)

Using the ~28μs/pixel throughput rate:

| Input Size | Pixels | Est. Processing (s) | vCPU Cost | Memory Cost | **Total Cost** | Status |
|-----------|--------|---------------------|-----------|-------------|---------------|--------|
| 480x320 | 153K | 4.3 | $0.00041 | $0.00009 | **$0.0005** | ✅ Works |
| 640x480 | 307K | 8.6 | $0.00083 | $0.00017 | **$0.0010** | ✅ Works |
| 1024x683 | 699K | 19.1 | $0.00183 | $0.00038 | **$0.0022** | ✅ Works |
| 1024x768 | 786K | 22.0 | $0.00211 | $0.00044 | **$0.0026** | ✅ Works |
| 1024x1536 | 1.57M | 46.9 | $0.00450 | $0.00094 | **$0.0054** | ✅ Works (slow) |
| 1920x1080 | 2.07M | ~58.0 | $0.00557 | $0.00116 | **$0.0067** | ⚠️ Borderline |
| 1920x1280 | 2.46M | ~68.8 | $0.00661 | $0.00138 | **$0.0080** | ❌ Fails (500) |
| 3000x4500 | 13.5M | ~378.0 | $0.03629 | $0.00756 | **$0.0439** | ❌ Fails (504) |

### Revised Cost Summary

All images **under 1024px** are well within the $0.05 budget:
- Small (≤640px): **$0.001/image** (50x under budget)
- Medium (≤1024px): **$0.003–0.005/image** (10-17x under budget)

Images **1920px+** currently **cannot be processed** on CPU-only Cloud Run (4 vCPU, 8 GiB).

## Recommendations

### Immediate (MVP)
1. **Cap input size at 1024px max dimension** for CPU-only processing
2. Add input validation to reject images >1024px (or auto-downscale before upscale)
3. Convert output from PNG to WebP/JPEG to reduce delivery size (25MB PNG → ~2-3MB WebP)

### Future (Post-MVP)
1. **GPU instances required** for 1920px+ images — benchmark T4/L4 GPU Cloud Run
2. Consider tiled processing for large images (process in 512x512 chunks, stitch)
3. Add progress webhooks for images taking >10s
4. Investigate why synthetic 1920x1080 succeeded but real photos at same size fail (instance variance? memory fragmentation?)

### Maximum Viable Input Sizes (CPU-only)

| Max Input Dimension | Processing Time | Cost | UX Viability |
|--------------------|----------------|------|-------------|
| 640px | <10s | $0.001 | ✅ Good |
| 1024px | 20-47s | $0.003-0.005 | ⚠️ Acceptable with progress bar |
| 1536px | ~47s | $0.005 | ⚠️ Only if portrait-oriented |
| 1920px+ | Fails | — | ❌ Needs GPU |
