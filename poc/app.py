"""Real-ESRGAN upscaling POC — FastAPI service."""

import io
import os
import time
import urllib.request

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
from basicsr.archs.rrdbnet_arch import RRDBNet
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import Response
from PIL import Image
from realesrgan import RealESRGANer
from realesrgan.archs.srvgg_arch import SRVGGNetCompact

app = FastAPI(title="ESRGAN POC")

MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
MODEL_PATH = "/tmp/realesr-general-x4v3.pth"

upsampler = None


def _download_model():
    if not os.path.exists(MODEL_PATH):
        print(f"Downloading model from {MODEL_URL} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Model downloaded.")


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
    print("Model loaded and ready.")


@app.on_event("startup")
async def startup():
    _load_model()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upscale")
async def upscale(
    file: UploadFile = File(...),
    scale: int = Query(4, ge=2, le=4),
):
    raw = await file.read()

    # Decode image
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
    if img is None:
        return Response(content="Invalid image", status_code=400)

    h, w = img.shape[:2]

    t0 = time.perf_counter()
    output, _ = upsampler.enhance(img, outscale=scale)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Encode to PNG
    _, buf = cv2.imencode(".png", output)

    oh, ow = output.shape[:2]
    headers = {
        "X-Processing-Time-Ms": f"{elapsed_ms:.1f}",
        "X-Input-Size": f"{w}x{h}",
        "X-Output-Size": f"{ow}x{oh}",
    }

    return Response(content=buf.tobytes(), media_type="image/png", headers=headers)
