from pathlib import Path
from app.config import settings


class StorageService:
    def __init__(self):
        self.base_dir = Path(settings.TEMP_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, job_id: str, ext: str, contents: bytes) -> Path:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / f"input{ext}"
        input_path.write_bytes(contents)
        return input_path

    def get_output_path(self, job_id: str) -> Path:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir / "output.png"


storage_service = StorageService()
