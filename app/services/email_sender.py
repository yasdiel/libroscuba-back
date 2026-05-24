"""Envío de correos (SMTP). En desarrollo sin SMTP, imprime el código en logs."""

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def _send_sync(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def send_register_otp_email(to_email: str, code: str) -> None:
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

    if not settings.smtp_configured:
        missing = ", ".join(settings.smtp_missing_fields())
        logger.warning(
            "[LibrosCuba] SMTP no configurado (faltan: %s). OTP para %s: %s",
            missing or "desconocido",
            to_email,
            code,
        )
        if os.getenv("RENDER"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "El servidor de correo no está configurado. "
                    f"Revisa en Render: {missing}. "
                    "Los nombres deben ser SMTP_HOST, SMTP_USER, SMTP_PASSWORD "
                    "(no SMPT)."
                ),
            )
        return

    try:
        await asyncio.to_thread(_send_sync, to_email, subject, body)
        logger.info("[LibrosCuba] OTP enviado por correo a %s", to_email)
    except smtplib.SMTPAuthenticationError as e:
        logger.exception("SMTP auth failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No se pudo autenticar con Gmail. Usa una contraseña de aplicación "
                "(no la contraseña normal) en SMTP_PASSWORD."
            ),
        ) from e
    except Exception as e:
        logger.exception("SMTP send failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo enviar el correo. Intenta de nuevo en unos minutos.",
        ) from e
