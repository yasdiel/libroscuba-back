"""Denuncias de libros y moderación."""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.report import REPORT_REASONS, ReportStatus
from app.services.cloudinary_service import delete_image
REPORT_ALREADY_MSG = "Este libro ya ha sido reportado."
REPORT_CLOSED_MSG = "Este libro no puede volver a ser denunciado."


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_report(db: AsyncIOMotorDatabase, book_id: str) -> Optional[dict[str, Any]]:
    return await db.book_reports.find_one({"_id": book_id})


async def create_book_report(
    db: AsyncIOMotorDatabase,
    *,
    book_id: str,
    reporter_id: Optional[str],
    reason: str,
    details: Optional[str],
) -> None:
    if reason not in REPORT_REASONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Motivo de reporte inválido",
        )

    book = await db.books.find_one({"_id": book_id})
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")

    if reporter_id and book["owner_id"] == reporter_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes reportar tu propio libro",
        )

    owner = await db.users.find_one({"_id": book["owner_id"]})
    if owner and owner.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Libro no encontrado",
        )

    existing = await get_report(db, book_id)
    if existing:
        st = existing.get("status", "pending")
        if st == "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=REPORT_ALREADY_MSG,
            )
        if st == "invalid":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=REPORT_CLOSED_MSG,
            )
        # valid: book should be gone; allow new report if book still exists
        if st == "valid":
            await db.book_reports.delete_one({"_id": book_id})

    now = _now()
    await db.book_reports.insert_one(
        {
            "_id": book_id,
            "book_id": book_id,
            "owner_id": book["owner_id"],
            "reporter_id": reporter_id,
            "reporter_anonymous": reporter_id is None,
            "reason": reason,
            "details": (details or "").strip() or None,
            "status": "pending",
            "created_at": now,
            "resolved_at": None,
            "resolved_by": None,
            "book_snapshot": {
                "titulo": book.get("titulo"),
                "autor": book.get("autor"),
                "precio": book.get("precio"),
                "foto_url": book.get("foto_url"),
                "estado": book.get("estado"),
                "provincia": book.get("provincia"),
                "municipio": book.get("municipio"),
            },
        }
    )


async def ban_user(
    db: AsyncIOMotorDatabase,
    user_id: str,
    *,
    reason: Optional[str],
    admin_id: str,
) -> None:
    doc = await db.users.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    if doc.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede banear un administrador",
        )
    now = _now()
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {
                "is_banned": True,
                "banned_at": now,
                "ban_reason": (reason or "").strip() or None,
                "banned_by": admin_id,
            }
        },
    )


async def unban_user(db: AsyncIOMotorDatabase, user_id: str) -> None:
    doc = await db.users.find_one({"_id": user_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": {"is_banned": False},
            "$unset": {"banned_at": "", "ban_reason": "", "banned_by": ""},
        },
    )


async def delete_book_and_images(db: AsyncIOMotorDatabase, book_id: str) -> None:
    doc = await db.books.find_one({"_id": book_id})
    if doc:
        await delete_image(doc.get("foto_url", ""), doc.get("cloudinary_public_id"))
        await db.books.delete_one({"_id": book_id})


async def remove_all_user_books(db: AsyncIOMotorDatabase, user_id: str) -> None:
    async for book in db.books.find({"owner_id": user_id}):
        await delete_image(book.get("foto_url", ""), book.get("cloudinary_public_id"))
    await db.books.delete_many({"owner_id": user_id})


async def resolve_book_report(
    db: AsyncIOMotorDatabase,
    book_id: str,
    *,
    decision: str,
    ban_owner: bool,
    admin_id: str,
) -> None:
    report = await get_report(db, book_id)
    if not report or report.get("status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado o ya resuelto",
        )

    now = _now()
    owner_id = report.get("owner_id")

    if decision == "valid":
        await delete_book_and_images(db, book_id)
        if ban_owner and owner_id:
            await ban_user(
                db,
                owner_id,
                reason="Reporte válido de publicación",
                admin_id=admin_id,
            )
            await remove_all_user_books(db, owner_id)
        await db.book_reports.update_one(
            {"_id": book_id},
            {
                "$set": {
                    "status": "valid",
                    "resolved_at": now,
                    "resolved_by": admin_id,
                }
            },
        )
        return

    if decision == "invalid":
        await db.book_reports.update_one(
            {"_id": book_id},
            {
                "$set": {
                    "status": "invalid",
                    "resolved_at": now,
                    "resolved_by": admin_id,
                }
            },
        )
        return

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decisión inválida")


async def list_pending_reports(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async for report in db.book_reports.find({"status": "pending"}).sort("created_at", -1):
        book_id = report["_id"]
        book = await db.books.find_one({"_id": book_id})
        snap = report.get("book_snapshot") or {}
        owner = None
        if book:
            owner = await db.users.find_one({"_id": book["owner_id"]})
        elif report.get("owner_id"):
            owner = await db.users.find_one({"_id": report["owner_id"]})

        items.append(
            {
                "book_id": book_id,
                "report_status": report.get("status", "pending"),
                "reason": report.get("reason", ""),
                "details": report.get("details"),
                "reporter_id": report.get("reporter_id"),
                "reported_at": report.get("created_at"),
                "titulo": (book or snap).get("titulo") or "—",
                "autor": (book or snap).get("autor") or "—",
                "precio": float((book or snap).get("precio") or 0),
                "foto_url": (book or snap).get("foto_url") or "",
                "estado": (book or snap).get("estado") or "usado",
                "provincia": (book or snap).get("provincia") or "",
                "municipio": (book or snap).get("municipio") or "",
                "owner_id": report.get("owner_id") or (book.get("owner_id") if book else ""),
                "owner_nombre_tienda": owner.get("nombre_tienda") if owner else None,
                "owner_whatsapp": owner.get("whatsapp_number") if owner else None,
            }
        )
    return items


async def list_banned_users(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async for doc in db.users.find({"is_banned": True}).sort("banned_at", -1):
        count = await db.books.count_documents({"owner_id": str(doc["_id"])})
        items.append(
            {
                "id": str(doc["_id"]),
                "nombre_tienda": doc.get("nombre_tienda", ""),
                "whatsapp_number": doc.get("whatsapp_number", ""),
                "provincia": doc.get("provincia", ""),
                "municipio": doc.get("municipio", ""),
                "banned_at": doc.get("banned_at") or _now(),
                "ban_reason": doc.get("ban_reason"),
                "book_count": count,
            }
        )
    return items


async def banned_owner_ids(db: AsyncIOMotorDatabase) -> list[str]:
    return [doc["_id"] async for doc in db.users.find({"is_banned": True}, {"_id": 1})]


def ensure_user_not_banned(user_doc: dict) -> None:
    if user_doc.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está suspendida. Contacta al administrador.",
        )
