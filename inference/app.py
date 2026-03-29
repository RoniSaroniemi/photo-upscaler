"""Real-ESRGAN production inference service."""

import asyncio
import io
import logging
import os
import time
import urllib.request
from contextlib import asynccontextmanager

# Patch for basicsr + newer torchvision compatibility
import torchvision.transforms.functional as F

if not hasattr(F, "rgb_to_grayscale"):
    F.rgb_to_grayscale = F.to_grayscale
import sys
import types

functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
functional_tensor.rgb_to_grayscale = F.rgb_to_grayscale
sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor
# End patch

import cv2
import numpy as np
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image
from realesrgan import RealESRGANer
from realesrgan.archs.srvgg_arch import SRVGGNetCompact

logger = logging.getLogger("inference")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
MODEL_PATH = "/tmp/realesr-general-x4v3.pth"

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DIMENSION = 1024
PROCESSING_TIMEOUT = 90  # seconds

upsampler = None


def _download_model():
    if not os.path.exists(MODEL_PATH):
        logger.info("Downloading model from %s ...", MODEL_URL)
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        logger.info("Model downloaded.")


def _load_model():
    global upsampler
    _download_model()

    model = SRVGGNetCompact(
        num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type="prelu"
    )

    upsampler = RealESRGANer(
        scale=4,
        model_path=MODEL_PATH,
        dni_weight=None,
        model=model,
        tile=256,
        tile_pad=10,
        pre_pad=0,
        half=False,
    )
    logger.info("Model loaded and ready.")


@asynccontextmanager
async def lifespan(app):
    _load_model()
    yield


app = FastAPI(title="Inference Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": bool(upsampler), "version": "1.0.0"}


@app.get("/estimate")
async def estimate(
    width: int = Query(..., gt=0),
    height: int = Query(..., gt=0),
):
    estimated_seconds = round((width * height * 28) / 1_000_000, 1)
    return {
        "estimated_seconds": estimated_seconds,
        "estimated_cost_usd": 0.0,
    }


@app.post("/upscale")
async def upscale(
    file: UploadFile = File(...),
    scale: int = Query(4, ge=2, le=4),
):
    # Read and validate file size
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        return JSONResponse(
            status_code=413,
            content={"error": "File too large", "max_mb": 10},
        )

    # Decode image
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
    if img is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid image"},
        )

    h, w = img.shape[:2]

    # Validate dimensions
    if max(w, h) > MAX_DIMENSION:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Image too large",
                "max_dimension": MAX_DIMENSION,
                "actual": f"{w}x{h}",
            },
        )

    logger.info("Processing: input=%dx%d scale=%d", w, h, scale)

    # Process with timeout
    t0 = time.perf_counter()
    try:
        output, _ = await asyncio.wait_for(
            asyncio.to_thread(upsampler.enhance, img, outscale=scale),
            timeout=PROCESSING_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "Processing timeout"},
        )
    except Exception:
        logger.exception("Processing failed")
        return JSONResponse(
            status_code=500,
            content={"error": "Processing failed"},
        )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Encode to WebP
    pil_img = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_img.save(buf, format="WEBP", quality=90)
    webp_bytes = buf.getvalue()

    oh, ow = output.shape[:2]
    logger.info(
        "Done: output=%dx%d time=%.1fms size=%d bytes",
        ow, oh, elapsed_ms, len(webp_bytes),
    )

    headers = {
        "X-Processing-Time-Ms": f"{elapsed_ms:.1f}",
        "X-Input-Size": f"{w}x{h}",
        "X-Output-Size": f"{ow}x{oh}",
    }

    return Response(content=webp_bytes, media_type="image/webp", headers=headers)
