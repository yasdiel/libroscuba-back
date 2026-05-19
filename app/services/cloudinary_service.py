import re
from typing import Optional
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from app.config import settings


def configure_cloudinary() -> None:
    if settings.cloudinary_cloud_name:
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )


def extract_public_id(url: str) -> Optional[str]:
    if not url or "cloudinary.com" not in url:
        return None
    match = re.search(r"/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z]+)?$", url.split("?")[0])
    if match:
        return match.group(1)
    return None


async def delete_image(url: str, public_id: Optional[str] = None) -> None:
    configure_cloudinary()
    pid = public_id or extract_public_id(url)
    if not pid:
        return
    try:
        cloudinary.uploader.destroy(pid, invalidate=True)
    except Exception:
        pass


def get_upload_signature(folder: str = "libroscuba") -> dict:
    configure_cloudinary()
    import time

    timestamp = int(time.time())
    params = {"timestamp": timestamp, "folder": folder}
    signature = cloudinary.utils.api_sign_request(
        params, settings.cloudinary_api_secret
    )
    return {
        "signature": signature,
        "timestamp": timestamp,
        "api_key": settings.cloudinary_api_key,
        "cloud_name": settings.cloudinary_cloud_name,
        "folder": folder,
    }
