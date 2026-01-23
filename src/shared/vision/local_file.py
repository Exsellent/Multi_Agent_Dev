import base64
import logging
from pathlib import Path

from .base import VisionProvider

logger = logging.getLogger("vision.local_file")


class LocalFileVisionService:
    """
    Converts local files to base64 and delegates analysis to VisionProvider
    """

    def __init__(self, provider: VisionProvider):
        self.provider = provider

    async def analyze_file(self, file_path: str, prompt: str) -> str:
        """
        Read local file, convert to base64, and analyze
        """
        src = Path(file_path)

        if not src.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read file and encode to base64
        with open(src, "rb") as f:
            image_bytes = f.read()

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # Determine media type
        media_type = self._get_media_type(src.suffix)
        image_data_url = f"data:{media_type};base64,{image_base64}"

        logger.info("Local image encoded to base64", extra={
            "file": str(src),
            "size_bytes": len(image_bytes),
            "media_type": media_type
        })

        return await self.provider.analyze(
            prompt=prompt,
            image_url=image_data_url
        )

    def _get_media_type(self, suffix: str) -> str:
        """Get MIME type based on file extension"""
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }
        return mime_types.get(suffix.lower(), "image/png")
