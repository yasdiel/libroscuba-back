from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.models.user import UserInDB
from app.services.cloudinary_service import get_upload_signature
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.get("/signature")
async def upload_signature(current: UserInDB = Depends(get_current_user)):
    if not settings.cloudinary_cloud_name or not settings.cloudinary_api_secret:
        raise HTTPException(
            status_code=503,
            detail="Cloudinary no configurado. Usa una URL de imagen directa en la demo.",
        )
    return get_upload_signature()
