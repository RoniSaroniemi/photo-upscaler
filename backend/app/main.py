from fastapi import FastAPI

from app.database import init_db
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.payments import router as payments_router
from app.routes.upload import router as upload_router

app = FastAPI(title="Photo Upscaler API", version="0.2.0")

app.include_router(health_router)
app.include_router(upload_router)
app.include_router(auth_router)
app.include_router(payments_router)


@app.on_event("startup")
def startup():
    init_db()
