"""Códigos OTP por email para verificación de registro."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings

OTP_LENGTH = 6
MAX_VERIFY_ATTEMPTS = 5
MAX_SENDS_PER_WINDOW = 3
SEND_WINDOW_MINUTES = 15


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_code(email: str, code: str) -> str:
    payload = f"{normalize_email(email)}:{code}:{settings.jwt_secret}"
    return hashlib.sha256(payload.encode()).hexdigest()


def generate_otp_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def _otp_expires_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)


async def email_already_registered(db: AsyncIOMotorDatabase, email: str) -> bool:
    key = normalize_email(email)
    doc = await db.users.find_one({"email": key}, {"_id": 1})
    return doc is not None


async def create_and_store_otp(db: AsyncIOMotorDatabase, email: str) -> str:
    """Genera OTP, lo guarda y devuelve el código en claro (solo para enviar por email)."""
    key = normalize_email(email)
    now = datetime.now(timezone.utc)
    existing = await db.email_otps.find_one({"_id": key})

    if existing:
        window_start = now - timedelta(minutes=SEND_WINDOW_MINUTES)
        send_times = []
        for t in existing.get("send_times", []):
            if not isinstance(t, datetime):
                continue
            aware = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
            if aware >= window_start:
                send_times.append(aware)
        if len(send_times) >= MAX_SENDS_PER_WINDOW:
            raise ValueError(
                "Demasiados intentos. Espera unos minutos antes de pedir otro código."
            )

    code = generate_otp_code()
    send_times = (existing.get("send_times", []) if existing else []) + [now]
    await db.email_otps.update_one(
        {"_id": key},
        {
            "$set": {
                "code_hash": _hash_code(key, code),
                "expires_at": _otp_expires_at(),
                "attempts": 0,
                "send_times": send_times[-MAX_SENDS_PER_WINDOW:],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return code


async def verify_otp(db: AsyncIOMotorDatabase, email: str, code: str) -> bool:
    key = normalize_email(email)
    doc = await db.email_otps.find_one({"_id": key})
    if not doc:
        return False

    now = datetime.now(timezone.utc)
    expires_at = doc.get("expires_at")
    if not expires_at or expires_at.replace(tzinfo=timezone.utc) < now:
        await db.email_otps.delete_one({"_id": key})
        return False

    attempts = int(doc.get("attempts", 0)) + 1
    if attempts > MAX_VERIFY_ATTEMPTS:
        await db.email_otps.delete_one({"_id": key})
        return False

    expected = doc.get("code_hash", "")
    supplied = _hash_code(key, code.strip())
    if not hmac.compare_digest(expected, supplied):
        await db.email_otps.update_one({"_id": key}, {"$set": {"attempts": attempts}})
        return False

    await db.email_otps.delete_one({"_id": key})
    return True
