"""Envío de OTP por correo: Resend (HTTPS, producción) o SMTP (desarrollo local)."""

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

import httpx
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

RENDER_SMTP_HINT = (
    "Render no permite conexiones SMTP salientes (Gmail en puerto 587). "
    "Crea una cuenta gratis en https://resend.com y configura RESEND_API_KEY y RESEND_FROM."
)


def _otp_email_content(code: str) -> tuple[str, str]:
    subject = f"Tu código LibrosCuba: {code}"
    minutes = settings.otp_expire_minutes
    body = (
        f"Hola,\n\n"
        f"Tu código de verificación para crear tu tienda en LibrosCuba es:\n\n"
        f"  {code}\n\n"
        f"Válido durante {minutes} minutos. No compartas este código con nadie.\n\n"
        f"Si no solicitaste este correo, ignóralo.\n\n"
        f"— LibrosCuba"
    )
    return subject, body


def _send_sync_smtp(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def _send_via_resend(to_email: str, subject: str, body: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
        )
    if response.status_code >= 400:
        detail = response.text[:500]
        logger.error("Resend API error %s: %s", response.status_code, detail)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo enviar el correo. Revisa RESEND_FROM y el dominio en Resend.",
        )


async def send_register_otp_email(to_email: str, code: str) -> None:
    subject, body = _otp_email_content(code)

    if not settings.email_configured:
        missing = ", ".join(settings.email_missing_env())
        logger.warning(
            "[LibrosCuba] Email no configurado (%s). OTP para %s: %s",
            missing,
            to_email,
            code,
        )
        if os.getenv("RENDER"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Correo no configurado. En Render usa Resend: {missing}",
            )
        return

    if settings.resend_configured:
        try:
            await _send_via_resend(to_email, subject, body)
            logger.info("[LibrosCuba] OTP enviado vía Resend a %s", to_email)
            return
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Resend send failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo enviar el correo. Intenta de nuevo.",
            ) from e

    if os.getenv("RENDER"):
        logger.error("[LibrosCuba] SMTP en Render bloqueado. %s", RENDER_SMTP_HINT)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=RENDER_SMTP_HINT,
        )

    try:
        await asyncio.to_thread(_send_sync_smtp, to_email, subject, body)
        logger.info("[LibrosCuba] OTP enviado vía SMTP a %s", to_email)
    except smtplib.SMTPAuthenticationError as e:
        logger.exception("SMTP auth failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No se pudo autenticar con Gmail. Usa una contraseña de aplicación "
                "en SMTP_PASSWORD."
            ),
        ) from e
    except OSError as e:
        logger.exception("SMTP network error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=RENDER_SMTP_HINT if os.getenv("RENDER") else str(e),
        ) from e
    except Exception as e:
        logger.exception("SMTP send failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo enviar el correo. Intenta de nuevo.",
        ) from e
