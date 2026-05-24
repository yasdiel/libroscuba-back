"""Envío de correos (SMTP). En desarrollo sin SMTP, imprime el código en logs."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_from
        and settings.smtp_user
        and settings.smtp_password
    )


def _send_sync(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    if settings.smtp_user and settings.smtp_password:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
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

    if not _smtp_configured():
        logger.warning(
            "[LibrosCuba] SMTP no configurado. OTP para %s: %s (válido %s min)",
            to_email,
            code,
            minutes,
        )
        return

    await asyncio.to_thread(_send_sync, to_email, subject, body)
