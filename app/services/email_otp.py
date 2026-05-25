"""OTP de registro por email vía OTP Cuba (otp.noxcreation.dev)."""

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.services.otpcuba_client import OTPCubaError, send_email_otp, verify_email_otp

MAX_SENDS_PER_WINDOW = 3
SEND_WINDOW_MINUTES = 15


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def email_already_registered(db: AsyncIOMotorDatabase, email: str) -> bool:
    key = normalize_email(email)
    doc = await db.users.find_one({"email": key}, {"_id": 1})
    return doc is not None


def _count_recent_sends(existing: dict | None, now: datetime) -> list[datetime]:
    if not existing:
        return []
    window_start = now - timedelta(minutes=SEND_WINDOW_MINUTES)
    send_times: list[datetime] = []
    for t in existing.get("send_times", []):
        if not isinstance(t, datetime):
            continue
        aware = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        if aware >= window_start:
            send_times.append(aware)
    return send_times


async def send_register_email_otp(db: AsyncIOMotorDatabase, email: str) -> None:
    """
    Envía OTP por correo con OTP Cuba y guarda el hash en MongoDB para verificar después.
    Solo email; no usa SMS ni teléfono.
    """
    key = normalize_email(email)
    now = datetime.now(timezone.utc)
    existing = await db.email_otps.find_one({"_id": key})

    send_times = _count_recent_sends(existing, now)
    if len(send_times) >= MAX_SENDS_PER_WINDOW:
        raise ValueError(
            "Demasiados intentos. Espera unos minutos antes de pedir otro código."
        )

    result = await send_email_otp(key)
    send_times.append(now)

    await db.email_otps.update_one(
        {"_id": key},
        {
            "$set": {
                "otpcuba_hash": result.hash,
                "expires_at": result.expires_at,
                "send_times": send_times[-MAX_SENDS_PER_WINDOW:],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def verify_register_email_otp(
    db: AsyncIOMotorDatabase, email: str, code: str
) -> bool:
    """Verifica el código con OTP Cuba usando el hash guardado para ese email."""
    key = normalize_email(email)
    doc = await db.email_otps.find_one({"_id": key})
    if not doc:
        return False

    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at")
    if expires_at:
        aware = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if aware < now:
            await db.email_otps.delete_one({"_id": key})
            return False

    otp_hash = doc.get("otpcuba_hash")
    if not otp_hash:
        await db.email_otps.delete_one({"_id": key})
        return False

    try:
        await verify_email_otp(str(otp_hash), code)
    except OTPCubaError as e:
        if e.status_code in (400, 404):
            return False
        raise

    await db.email_otps.delete_one({"_id": key})
    return True
