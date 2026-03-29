from fastapi import FastAPI
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router

app = FastAPI(title="Photo Upscaler API", version="0.1.0")

app.include_router(health_router)
app.include_router(upload_router)
