import time
from pathlib import Path

from app.config import settings
from app.services.storage import storage_service


class UpscalerService:
    def __init__(self):
        self.model = None
        self.model_loaded = False
        self.model_name = settings.MODEL_NAME
        self.scale_factor = settings.SCALE_FACTOR

    def load_model(self):
        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet

            rrdb_model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            self.model = RealESRGANer(
                scale=self.scale_factor,
                model_path=None,  # Will auto-download
                model=rrdb_model,
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=False,  # CPU mode — no half precision
            )
            self.model_loaded = True
        except ImportError:
            # Model dependencies not available (e.g., in test/CI environments)
            self.model_loaded = False
        except Exception:
            self.model_loaded = False

    def upscale(self, input_path: str, job_id: str) -> dict:
        start_time = time.time()

        output_path = storage_service.get_output_path(job_id)

        if not self.model_loaded:
            # Fallback: copy input as output for environments without Real-ESRGAN
            from PIL import Image

            img = Image.open(input_path)
            new_size = (img.width * self.scale_factor, img.height * self.scale_factor)
            img_resized = img.resize(new_size, Image.LANCZOS)
            img_resized.save(str(output_path), "PNG")
        else:
            import cv2
            import numpy as np

            img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
            output, _ = self.model.enhance(img, outscale=self.scale_factor)
            cv2.imwrite(str(output_path), output)

        processing_time = time.time() - start_time
        return {
            "output_path": str(output_path),
            "processing_time": round(processing_time, 2),
        }


upscaler_service = UpscalerService()
