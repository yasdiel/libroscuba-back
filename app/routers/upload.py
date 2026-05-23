from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.models.user import UserInDB
from app.services.cloudinary_service import get_upload_signature
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.get("/signature")
async def upload_signature(
    folder: str = Query("libroscuba", max_length=120),
    _: UserInDB = Depends(get_current_user),
):
    if not settings.cloudinary_cloud_name or not settings.cloudinary_api_secret:
        raise HTTPException(
            status_code=503,
            detail="Cloudinary no configurado en el servidor (CLOUDINARY_API_SECRET).",
        )
    safe_folder = folder.strip().replace("..", "") or "libroscuba"
    return get_upload_signature(safe_folder)
