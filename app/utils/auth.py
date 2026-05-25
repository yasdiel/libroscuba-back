import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.database import get_db
from app.models.user import UserInDB
# bcrypt rounds = 10 (≈100ms en CPU normal; el default 12 toma ~400ms y
# ahoga el plan free de Render). Suficiente para una demo.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=10)
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Versión síncrona, úsala solo en scripts (seed_data, etc.)."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Versión síncrona, úsala solo en scripts."""
    return pwd_context.verify(plain, hashed)


async def hash_password_async(password: str) -> str:
    """bcrypt es CPU-bound; lo movemos a thread para no bloquear el event loop."""
    return await asyncio.to_thread(pwd_context.hash, password)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(pwd_context.verify, plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


def user_from_doc(doc: dict) -> UserInDB:
    return UserInDB(
        id=str(doc["_id"]),
        hashed_password=doc["hashed_password"],
        whatsapp_number=doc["whatsapp_number"],
        provincia=doc["provincia"],
        municipio=doc["municipio"],
        nombre_tienda=doc["nombre_tienda"],
        municipios_envio=doc.get("municipios_envio", []) or [],
        is_admin=doc.get("is_admin", False),
        is_banned=bool(doc.get("is_banned")),
        created_at=doc.get("created_at", datetime.now(timezone.utc)),
        banned_at=doc.get("banned_at"),
        ban_reason=doc.get("ban_reason"),
        foto_tienda_url=doc.get("foto_tienda_url"),
        tienda_slug=doc.get("tienda_slug") or "",
        email=doc.get("email"),
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserInDB:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    doc = await get_db().users.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    user = user_from_doc(doc)
    if not user.is_admin and user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está suspendida. Contacta al administrador.",
        )
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UserInDB]:
    if not credentials:
        return None
    user_id = decode_token(credentials.credentials)
    if not user_id:
        return None
    doc = await get_db().users.find_one({"_id": user_id})
    if not doc:
        return None
    return user_from_doc(doc)


async def require_admin(current: UserInDB = Depends(get_current_user)) -> UserInDB:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return current
