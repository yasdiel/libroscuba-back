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


def _is_cloudflare_challenge(status_code: int, raw_text: str, content_type: str) -> bool:
    if status_code not in (403, 503):
        return False
    lower = raw_text.lower()
    if "just a moment" in lower or "challenges.cloudflare.com" in lower:
        return True
    if "cloudflare" in lower and "<!doctype html" in lower:
        return True
    return "text/html" in content_type and "<!doctype html" in lower


def _auth_headers() -> dict[str, str]:
    return {
        "x-api-key": settings.otpcuba_api_key,
        "x-token-secret": settings.otpcuba_token_secret,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "LibrosCuba/1.0 (server; registration-otp)",
    }


def _parse_expires_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_message(data: dict | None, fallback: str, raw_text: str = "") -> str:
    if data:
        for key in ("error", "message", "detail", "msg"):
            value = data.get(key)
            if value:
                return str(value)
    text = (raw_text or "").strip()
    if text and text.startswith("{"):
        return fallback
    if text and len(text) <= 500:
        return text
    return fallback


def _user_message_for_status(status_code: int, api_message: str) -> str:
    """Mensajes claros para el usuario según el código HTTP de OTP Cuba."""
    lower = api_message.lower()
    if status_code == 402 or "saldo" in lower:
        return (
            "El saldo de OTP Cuba es solo para SMS. El registro por correo es gratuito; "
            "revisa que OTPCUBA_API_KEY y OTPCUBA_TOKEN_SECRET no estén intercambiados en Render."
        )
    if status_code == 403 and (
        "just a moment" in lower or "cloudflare" in lower or "<!doctype html" in lower
    ):
        return (
            "El proveedor OTP Cuba está bloqueado por Cloudflare desde el servidor de Render "
            "(no es falta de saldo: el email OTP es gratuito). Contacta a soporte de OTP Cuba / "
            "Nox Creation para permitir llamadas API desde servidores (ruta /api/v2/*) o desactivar "
            "el challenge para integraciones server-to-server."
        )
    if status_code == 403:
        return (
            "OTP Cuba rechazó el envío por correo (403). Revisa claves en Render "
            "(OTPCUBA_API_KEY = APP-..., OTPCUBA_TOKEN_SECRET = OTP-...) y que la app esté activa. "
            f"Detalle: {api_message}"
        )
    if status_code == 401:
        return (
            "Claves de OTP Cuba inválidas. En Render: OTPCUBA_API_KEY debe ser la clave APP-... "
            "y OTPCUBA_TOKEN_SECRET la clave OTP-... (no las intercambies)."
        )
    if status_code == 429:
        return api_message
    return api_message


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

    raw_text = response.text
    content_type = response.headers.get("content-type", "")
    data: dict | None = None
    if content_type.startswith("application/json"):
        try:
            data = response.json()
        except ValueError:
            data = None

    if _is_cloudflare_challenge(response.status_code, raw_text, content_type):
        logger.error(
            "OTP Cuba bloqueado por Cloudflare (respuesta HTML, no JSON). "
            "Las peticiones desde Render necesitan regla de bypass en otp.noxcreation.dev."
        )
        raise OTPCubaError(
            _user_message_for_status(403, "just a moment cloudflare"),
            status_code=403,
        )

    if response.status_code >= 400:
        api_msg = _error_message(data, "No se pudo enviar el código por correo.", raw_text)
        msg = _user_message_for_status(response.status_code, api_msg)
        logger.error(
            "OTP Cuba send %s: %s (body=%s)",
            response.status_code,
            api_msg,
            raw_text[:500],
        )
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

    raw_text = response.text
    content_type = response.headers.get("content-type", "")

    if _is_cloudflare_challenge(response.status_code, raw_text, content_type):
        raise OTPCubaError(
            _user_message_for_status(403, "just a moment cloudflare"),
            status_code=403,
        )

    if response.status_code < 400:
        return

    data: dict | None = None
    if content_type.startswith("application/json"):
        try:
            data = response.json()
        except ValueError:
            data = None

    msg = _error_message(data, "Código incorrecto o expirado.", raw_text)
    raise OTPCubaError(msg, status_code=response.status_code)


def raise_http_from_otpcuba(err: OTPCubaError) -> None:
    """Convierte OTPCubaError en HTTPException para las rutas FastAPI."""
    code = err.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
    if code == 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.message)
    if code in (401, 403, 402):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=err.message,
        )
    if code == 429:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=err.message)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=err.message,
    )
