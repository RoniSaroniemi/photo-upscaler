# Real-ESRGAN Feasibility Report for Google Cloud Run

## Summary

Cost per image is **$0.002-0.005** — well under the $0.05 target. Two viable approaches exist.

## Model Options

| Model | Architecture | Params | Size | Inference (CPU 4vCPU) | Best For |
|-------|-------------|--------|------|----------------------|----------|
| RealESRGAN_x4plus | RRDBNet (23 blocks) | ~16.7M | ~64 MB | 60-180s (too slow) | GPU only |
| realesr-general-x4v3 | SRVGGNetCompact | ~1.21M | ~4.7 MB | 15-40s | CPU POC |
| RealESRGAN_x4plus_anime_6B | RRDBNet (6 blocks) | ~6M | ~17 MB | - | Anime |
| realesr-animevideov3 | SRVGGNetCompact | ~1.21M | ~8 MB | - | Video |

## GO/NO-GO by Approach

### CPU + realesr-general-x4v3 — CONDITIONAL GO (Best for POC)
- 15-40s inference on 4 vCPU, borderline acceptable
- Cost: ~$0.002-0.005/image
- Container: ~1.5 GB
- Quality lower than x4plus but acceptable for general photos
- Risk: actual times need validation; cap input at 1024x768

### GPU (L4) + RealESRGAN_x4plus — GO (Best for Production)
- 3-8s inference, excellent UX
- Cost: ~$0.002/image
- Best quality with full model
- L4 GPU is GA in europe-west1, asia-southeast1 (us-central1 invitation-only)
- Cold start ~10-15s, acceptable if disclosed

### CPU + RealESRGAN_x4plus — NO-GO
- 60-180s+ per image, unacceptable UX

### ONNX Optimization — NO-GO as standalone strategy
- Minimal speedup over PyTorch for this architecture
- The real win is choosing lighter model, not the runtime

## Cost Breakdown

### CPU-Only (4 vCPU, 8 GiB) with realesr-general-x4v3
| Duration | CPU Cost | Memory Cost | Total |
|----------|----------|-------------|-------|
| 15s | $0.00144 | $0.00030 | ~$0.0017 |
| 40s | $0.00384 | $0.00080 | ~$0.0046 |

### GPU L4 (4 vCPU, 16 GiB, 1x L4) with RealESRGAN_x4plus
| Duration | GPU Cost | CPU+Mem Cost | Total |
|----------|----------|--------------|-------|
| 5s | $0.000934 | $0.000680 | ~$0.0016 |
| 8s | $0.001494 | $0.001088 | ~$0.0026 |

Cold starts add $0.001-0.004 to first request after scale-to-zero.

## Container Requirements

### CPU-Only (~1.5 GB)
- python:3.11-slim base
- torch + torchvision (CPU-only wheels): ~650 MB
- realesrgan + basicsr + facexlib: ~50 MB
- Model file: 4.7 MB (general-x4v3) or 64 MB (x4plus)

### GPU (~4-6 GB)
- nvidia/cuda:12.1 base
- PyTorch with CUDA: ~2.5 GB
- Model: 64 MB

### Existing Docker References
- nuvic/real-esrgan (Docker Hub)
- mkocot/real-esrgan-docker (GitHub)
- ashleykleynhans/runpod-worker-real-esrgan (RunPod serverless)

## Recommended POC Strategy

1. Build CPU container with realesr-general-x4v3
2. Deploy to Cloud Run (4 vCPU, 8 GiB)
3. Benchmark with real photos at various resolutions
4. If <30s: ship POC with CPU, add GPU for production
5. If >60s: pivot to GPU L4 (europe-west1)

## Comparison with Competitors

| Service | Cost/Image | Speed |
|---------|-----------|-------|
| Replicate (T4) | ~$0.005 | ~22s |
| Atlas Cloud | ~$0.0024 | - |
| **Us (CPU POC)** | **~$0.003** | **15-40s** |
| **Us (GPU prod)** | **~$0.002** | **3-8s** |
