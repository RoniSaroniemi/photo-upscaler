#!/usr/bin/env bash
# Benchmark script for ESRGAN POC on Cloud Run
set -euo pipefail

SERVICE_URL="${1:?Usage: benchmark.sh <cloud-run-url>}"
RESULTS_FILE="$(dirname "$0")/benchmark-results.md"
TMPDIR="$(mktemp -d)"

trap 'rm -rf "$TMPDIR"' EXIT

echo "=== ESRGAN POC Benchmark ==="
echo "Service: $SERVICE_URL"
echo ""

# Generate test images using Python/PIL
python3 -c "
from PIL import Image
import os, sys
sizes = [(640,480,'small'), (1024,768,'medium'), (1920,1080,'large')]
d = sys.argv[1]
for w,h,name in sizes:
    img = Image.new('RGB', (w,h), color=(100,150,200))
    # Add some variation so it's not a flat color
    import random; random.seed(42)
    pixels = img.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            r = min(255, 100 + (x * 37 + y * 13) % 100)
            g = min(255, 150 + (x * 17 + y * 29) % 80)
            b = min(255, 200 + (x * 7 + y * 41) % 50)
            pixels[x,y] = (r,g,b)
    path = os.path.join(d, f'test-{name}.jpg')
    img.save(path, quality=85)
    print(f'Created {path} ({w}x{h})')
" "$TMPDIR"

# Run benchmarks
declare -A SIZES=( ["small"]="640x480" ["medium"]="1024x768" ["large"]="1920x1080" )

cat > "$RESULTS_FILE" <<'HEADER'
# ESRGAN POC Benchmark Results

## Test Setup
- Model: realesr-general-x4v3 (SRVGGNetCompact, ~1.21M params)
- Scale: 4x
- Cloud Run config: 4 vCPU, 8 GiB RAM, CPU-only
- Concurrency: 1

## Results

| Image Size | Run | Total Time (s) | Processing Time (ms) | Output Size | Cold Start |
|-----------|-----|----------------|---------------------|-------------|------------|
HEADER

for size in small medium large; do
    echo "--- Testing $size (${SIZES[$size]}) ---"
    for run in 1 2 3; do
        is_cold="No"
        if [ "$size" = "small" ] && [ "$run" -eq 1 ]; then
            is_cold="Yes (first request)"
        fi

        result=$(curl -s -w "\n%{http_code}\n%{time_total}" \
            -X POST -F "file=@$TMPDIR/test-${size}.jpg" \
            -D "$TMPDIR/headers-${size}-${run}.txt" \
            "$SERVICE_URL/upscale" \
            --output "$TMPDIR/out-${size}-${run}.png" 2>&1)

        http_code=$(echo "$result" | tail -2 | head -1)
        total_time=$(echo "$result" | tail -1)

        proc_time=$(grep -i 'x-processing-time-ms' "$TMPDIR/headers-${size}-${run}.txt" 2>/dev/null | awk '{print $2}' | tr -d '\r' || echo "N/A")
        output_size=$(grep -i 'x-output-size' "$TMPDIR/headers-${size}-${run}.txt" 2>/dev/null | awk '{print $2}' | tr -d '\r' || echo "N/A")

        echo "  Run $run: HTTP $http_code, Total=${total_time}s, Processing=${proc_time}ms"

        echo "| ${SIZES[$size]} | $run | $total_time | $proc_time | $output_size | $is_cold |" >> "$RESULTS_FILE"
    done
done

# Add cost analysis
cat >> "$RESULTS_FILE" <<'COST'

## Cost Analysis

Cloud Run pricing (us-central1, 2024):
- vCPU: $0.00002400/vCPU-second
- Memory: $0.00000250/GiB-second
- Requests: $0.40 per million

### Per-image cost estimate

| Component | Calculation | Cost |
|-----------|------------|------|
| vCPU (4 vCPU) | 4 × processing_time_s × $0.000024 | See below |
| Memory (8 GiB) | 8 × processing_time_s × $0.0000025 | See below |
| Request | 1 / 1,000,000 × $0.40 | $0.0000004 |

*Actual costs will be filled in based on benchmark results above.*

## Recommendation

*To be filled based on benchmark data: GO if cost < $0.05/image, NO-GO otherwise.*
COST

echo ""
echo "Results written to $RESULTS_FILE"
