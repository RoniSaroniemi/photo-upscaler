FROM python:3.11-slim

# System dependencies for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the Real-ESRGAN model at build time
RUN python -c "\
from basicsr.archs.rrdbnet_arch import RRDBNet; \
from realesrgan import RealESRGANer; \
model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4); \
upsampler = RealESRGANer(scale=4, model_path=None, model=model, tile=0); \
print('Model downloaded successfully')" || echo "Model pre-download skipped"

COPY app/ ./app/

ENV PORT=8080
ENV TEMP_DIR=/tmp/upscaler
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
