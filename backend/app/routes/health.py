from fastapi import APIRouter
from app.services.upscaler import upscaler_service

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "model_loaded": upscaler_service.model_loaded,
    }
