import os
from pathlib import Path


class Settings:
    PORT: int = int(os.getenv("PORT", "8080"))
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/upscaler")
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    MODEL_NAME: str = os.getenv("MODEL_NAME", "RealESRGAN_x4plus")
    SCALE_FACTOR: int = int(os.getenv("SCALE_FACTOR", "4"))

    COMPUTE_COST_PER_IMAGE: float = float(os.getenv("COMPUTE_COST_PER_IMAGE", "0.02"))
    PLATFORM_FEE_PER_IMAGE: float = float(os.getenv("PLATFORM_FEE_PER_IMAGE", "0.03"))

    ALLOWED_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".webp"}

    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    def __init__(self):
        Path(self.TEMP_DIR).mkdir(parents=True, exist_ok=True)


settings = Settings()
