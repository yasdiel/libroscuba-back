"""Cliente HTTP para OTP Cuba (envío y verificación OTP por email)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


class OTPCubaError(Exception):
    """Error devuelto por la API de OTP Cuba."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class OTPSendResult:
    hash: str
    expires_at: datetime
    is_sandbox: bool


def _auth_headers() -> dict[str, str]:
    return {
        "x-api-key": settings.otpcuba_api_key,
        "x-token-secret": settings.otpcuba_token_secret,
        "Content-Type": "application/json",
    }


def _parse_expires_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_message(data: dict | None, fallback: str) -> str:
    if not data:
        return fallback
    return str(data.get("error") or data.get("message") or fallback)


async def send_email_otp(email: str) -> OTPSendResult:
    """Solicita envío de OTP por correo (solo email, sin SMS)."""
    if not settings.otpcuba_configured:
        raise OTPCubaError(
            "OTP Cuba no configurado. Define OTPCUBA_API_KEY y OTPCUBA_TOKEN_SECRET.",
            status_code=503,
        )

    url = f"{settings.otpcuba_base_url.rstrip('/')}/api/v2/send"
    body = {
        "email": email,
        "expiresInSeconds": settings.otp_expire_minutes * 60,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=_auth_headers(), json=body)
    except httpx.RequestError as e:
        logger.exception("OTP Cuba send request failed")
        raise OTPCubaError(
            "No se pudo contactar el servicio de verificación por correo.",
            status_code=503,
        ) from e

    data: dict | None = None
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            data = response.json()
        except ValueError:
            data = None

    if response.status_code >= 400:
        msg = _error_message(data, "No se pudo enviar el código por correo.")
        logger.error("OTP Cuba send %s: %s", response.status_code, msg)
        raise OTPCubaError(msg, status_code=response.status_code)

    if not data or not data.get("hash"):
        raise OTPCubaError("Respuesta inválida del servicio OTP.", status_code=502)

    expires_raw = data.get("expiresAt")
    if expires_raw:
        expires_at = _parse_expires_at(str(expires_raw))
    else:
        from datetime import timedelta

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)

    logger.info("[LibrosCuba] OTP email solicitado vía OTP Cuba para %s", email)
    return OTPSendResult(
        hash=str(data["hash"]),
        expires_at=expires_at,
        is_sandbox=bool(data.get("isSandbox")),
    )


async def verify_email_otp(otp_hash: str, code: str) -> None:
    """Valida el código OTP con OTP Cuba. Lanza OTPCubaError si falla."""
    if not settings.otpcuba_configured:
        raise OTPCubaError(
            "OTP Cuba no configurado.",
            status_code=503,
        )

    url = f"{settings.otpcuba_base_url.rstrip('/')}/api/v2/verify"
    body = {"hash": otp_hash, "code": code.strip()}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=_auth_headers(), json=body)
    except httpx.RequestError as e:
        logger.exception("OTP Cuba verify request failed")
        raise OTPCubaError(
            "No se pudo verificar el código. Intenta de nuevo.",
            status_code=503,
        ) from e

    if response.status_code < 400:
        return

    data: dict | None = None
    if response.headers.get("content-type", "").startswith("application/json"):
        try:
            data = response.json()
        except ValueError:
            data = None

    msg = _error_message(data, "Código incorrecto o expirado.")
    raise OTPCubaError(msg, status_code=response.status_code)


def raise_http_from_otpcuba(err: OTPCubaError) -> None:
    """Convierte OTPCubaError en HTTPException para las rutas FastAPI."""
    code = err.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
    if code == 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.message)
    if code == 401:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de correo mal configurado. Revisa las claves en OTP Cuba.",
        )
    if code == 429:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err.message)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=err.message,
    )
