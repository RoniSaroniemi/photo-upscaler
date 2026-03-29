# ESRGAN POC Benchmark Results

## Test Setup
- Model: realesr-general-x4v3 (SRVGGNetCompact, ~1.21M params)
- Scale: 4x
- Cloud Run config: 4 vCPU, 8 GiB RAM, CPU-only
- Concurrency: 1
- Service URL: https://esrgan-poc-132808742560.us-central1.run.app
- Date: 2026-03-29

## Results

| Image Size | Run | Total Time (s) | Processing Time (ms) | Output Size | Cold Start |
|-----------|-----|----------------|---------------------|-------------|------------|
| 640x480 | 1 | 13.36 | 11,223 | 2560x1920 | Yes (first request) |
| 640x480 | 2 | 11.34 | 10,342 | 2560x1920 | No |
| 640x480 | 3 | 11.08 | 9,185 | 2560x1920 | No |
| 1024x768 | 1 | 31.77 | 28,693 | 4096x3072 | No |
| 1024x768 | 2 | 42.24 | 20,511 | 4096x3072 | No |
| 1024x768 | 3 | 31.31 | 28,810 | 4096x3072 | No |
| 1920x1080 | 1 | 83.79 | 78,012 | 7680x4320 | No |
| 1920x1080 | 2 | 80.52 | 74,601 | 7680x4320 | No |
| 1920x1080 | 3 | 78.30 | 72,631 | 7680x4320 | No |

### Summary by Size (warm averages)

| Input Size | Avg Processing Time | Output Size |
|-----------|-------------------|-------------|
| 640x480 (small) | ~10.2s | 2560x1920 |
| 1024x768 (medium) | ~26.0s | 4096x3072 |
| 1920x1080 (large) | ~75.1s | 7680x4320 |

### Cold Start
- First request cold start overhead: ~2-3s (13.4s total vs ~11.2s warm for small image)

## Cost Analysis

Cloud Run pricing (us-central1):
- vCPU: $0.00002400/vCPU-second
- Memory: $0.00000250/GiB-second
- Requests: $0.40 per million

### Per-image cost estimate

| Image Size | Processing (s) | vCPU Cost | Memory Cost | Total Cost |
|-----------|----------------|-----------|-------------|------------|
| 640x480 | 10.2 | 4 x 10.2 x $0.000024 = $0.00098 | 8 x 10.2 x $0.0000025 = $0.00020 | **$0.0012** |
| 1024x768 | 26.0 | 4 x 26.0 x $0.000024 = $0.00250 | 8 x 26.0 x $0.0000025 = $0.00052 | **$0.0030** |
| 1920x1080 | 75.1 | 4 x 75.1 x $0.000024 = $0.00721 | 8 x 75.1 x $0.0000025 = $0.00150 | **$0.0087** |

## Recommendation

**GO** — All image sizes come in well under the $0.05/image target:
- Small (640x480): $0.0012/image (42x under budget)
- Medium (1024x768): $0.0030/image (17x under budget)
- Large (1920x1080): $0.0087/image (6x under budget)

### Caveats
- Processing times are long for user experience (10s-75s for CPU-only)
- GPU instances would be faster but more expensive — worth benchmarking in next phase
- Real photos with more detail may take slightly longer than synthetic test images
- Cold start is minimal (~2-3s) due to pre-downloaded model weights
