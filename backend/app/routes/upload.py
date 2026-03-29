import math
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.database import deduct_balance, get_session_user
from app.services.storage import storage_service
from app.services.upscaler import upscaler_service

router = APIRouter()

SESSION_COOKIE = "session_id"

# In-memory job tracker (replaced by DB/Redis in production)
jobs: dict[str, dict] = {}


def _get_total_cost_cents() -> int:
    """Get total cost per image in cents."""
    return math.ceil((settings.COMPUTE_COST_PER_IMAGE + settings.PLATFORM_FEE_PER_IMAGE) * 100)


@router.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    # Check authentication
    session_id = request.cookies.get(SESSION_COOKIE)
    user = None
    if session_id:
        user = get_session_user(session_id)

    if not user:
        raise HTTPException(status_code=401, detail="Please log in to upscale images")

    # Check balance
    cost_cents = _get_total_cost_cents()
    if user["balance_cents"] < cost_cents:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient balance. This image costs ${cost_cents / 100:.2f}. "
            f"Your balance is ${user['balance_cents'] / 100:.2f}. Please add funds.",
        )

    # Validate extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    contents = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB.",
        )

    # Save input file
    job_id = str(uuid.uuid4())
    input_path = storage_service.save_upload(job_id, ext, contents)

    jobs[job_id] = {"status": "queued", "input_path": str(input_path), "output_path": None, "user_id": user["id"]}

    # Process synchronously for MVP (async worker in production)
    try:
        jobs[job_id]["status"] = "processing"
        result = upscaler_service.upscale(str(input_path), job_id)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["output_path"] = result["output_path"]
        jobs[job_id]["processing_time"] = result["processing_time"]

        # Deduct balance after successful processing
        new_balance = deduct_balance(
            user["id"],
            cost_cents,
            f"Image upscale: {file.filename or 'unknown'}",
        )
        if new_balance is not None:
            jobs[job_id]["new_balance_cents"] = new_balance
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

    return {
        "job_id": job_id,
        "status": jobs[job_id]["status"],
        "cost_cents": cost_cents,
        "new_balance_cents": jobs[job_id].get("new_balance_cents"),
    }


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "processing_time": job.get("processing_time"),
        "error": job.get("error"),
    }


@router.get("/download/{job_id}")
async def download_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Job status is '{job['status']}', not ready for download")
    output_path = job.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(output_path, media_type="image/png", filename=f"upscaled_{job_id}.png")


@router.get("/pricing")
async def get_pricing(width: int = 1920, height: int = 1080):
    compute_cost = settings.COMPUTE_COST_PER_IMAGE
    platform_fee = settings.PLATFORM_FEE_PER_IMAGE
    total = compute_cost + platform_fee
    return {
        "input_dimensions": {"width": width, "height": height},
        "output_dimensions": {"width": width * settings.SCALE_FACTOR, "height": height * settings.SCALE_FACTOR},
        "scale_factor": settings.SCALE_FACTOR,
        "cost_breakdown": {
            "compute": compute_cost,
            "platform_fee": platform_fee,
            "total": total,
        },
        "currency": "USD",
    }
