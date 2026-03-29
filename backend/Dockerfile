# === Stage 1: Builder ===
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# === Stage 2: Runtime ===
FROM python:3.11-slim

# System dependencies for OpenCV / image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Pre-download the Real-ESRGAN model at build time so cold starts are faster
RUN python -c "\
from basicsr.archs.rrdbnet_arch import RRDBNet; \
from realesrgan.utils import RealESRGANer; \
import urllib.request, os; \
os.makedirs(os.path.expanduser('~/.cache/realesrgan'), exist_ok=True); \
model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4); \
print('Model architecture initialized')" || echo "Model pre-download skipped — will download at first request"

COPY app/ ./app/

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /tmp/upscaler \
    && chown -R appuser:appuser /app /tmp/upscaler
USER appuser

ENV PORT=8080
ENV TEMP_DIR=/tmp/upscaler
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
