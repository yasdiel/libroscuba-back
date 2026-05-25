from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database import get_db
from app.models.book import BookWithOwner
from app.models.report import AdminReportedBook, BannedUserPublic, BookReportResolve
from app.models.user import UserInDB, UserStorePublic
from app.routers.books import book_from_doc
from app.services.book_reports import (
    list_banned_users,
    list_pending_reports,
    resolve_book_report,
    unban_user,
)
from app.services.cloudinary_service import delete_image
from app.utils.store_slug import ensure_tienda_slug_on_user
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def admin_stats(_: UserInDB = Depends(require_admin)):
    db = get_db()
    total_books = await db.books.count_documents({})
    total_stores = await db.users.count_documents(
        {"is_admin": {"$ne": True}, "is_banned": {"$ne": True}}
    )
    pending_reports = await db.book_reports.count_documents({"status": "pending"})
    banned_count = await db.users.count_documents({"is_banned": True})
    return {
        "total_libros_activos": total_books,
        "total_tiendas": total_stores,
        "reportes_pendientes": pending_reports,
        "cuentas_baneadas": banned_count,
    }


@router.get("/books", response_model=list[BookWithOwner])
async def admin_list_books(
    q: str | None = Query(None),
    _: UserInDB = Depends(require_admin),
):
    db = get_db()
    query = {}
    if q:
        query["$or"] = [
            {"titulo": {"$regex": q, "$options": "i"}},
            {"autor": {"$regex": q, "$options": "i"}},
        ]
    books = []
    async for doc in db.books.find(query).sort("fecha_creacion", -1):
        owner = await db.users.find_one({"_id": doc["owner_id"]})
        item = book_from_doc(doc, owner)
        books.append(
            BookWithOwner(
                **item.model_dump(),
                owner_whatsapp=owner.get("whatsapp_number") if owner else None,
            )
        )
    return books


@router.get("/reports", response_model=list[AdminReportedBook])
async def admin_list_reports(_: UserInDB = Depends(require_admin)):
    db = get_db()
    rows = await list_pending_reports(db)
    return [AdminReportedBook(**row) for row in rows]


@router.post("/reports/{book_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
async def admin_resolve_report(
    book_id: str,
    payload: BookReportResolve,
    admin: UserInDB = Depends(require_admin),
):
    db = get_db()
    await resolve_book_report(
        db,
        book_id,
        decision=payload.decision,
        ban_owner=payload.ban_owner,
        admin_id=admin.id,
    )
    return None


@router.get("/banned", response_model=list[BannedUserPublic])
async def admin_list_banned(_: UserInDB = Depends(require_admin)):
    db = get_db()
    rows = await list_banned_users(db)
    return [BannedUserPublic(**row) for row in rows]


@router.post("/banned/{user_id}/unban", status_code=status.HTTP_204_NO_CONTENT)
async def admin_unban_user(user_id: str, _: UserInDB = Depends(require_admin)):
    db = get_db()
    await unban_user(db, user_id)
    return None


@router.get("/stores", response_model=list[UserStorePublic])
async def admin_list_stores(
    q: str | None = Query(None),
    _: UserInDB = Depends(require_admin),
):
    db = get_db()
    query: dict = {"is_admin": {"$ne": True}, "is_banned": {"$ne": True}}
    if q:
        query["$or"] = [
            {"nombre_tienda": {"$regex": q, "$options": "i"}},
            {"provincia": {"$regex": q, "$options": "i"}},
            {"municipio": {"$regex": q, "$options": "i"}},
            {"whatsapp_number": {"$regex": q, "$options": "i"}},
        ]
    stores = []
    async for doc in db.users.find(query).sort("nombre_tienda", 1):
        if not doc.get("tienda_slug"):
            await ensure_tienda_slug_on_user(db, doc)
            doc = await db.users.find_one({"_id": doc["_id"]}) or doc
        count = await db.books.count_documents({"owner_id": str(doc["_id"])})
        stores.append(
            UserStorePublic(
                id=str(doc["_id"]),
                nombre_tienda=doc["nombre_tienda"],
                tienda_slug=doc["tienda_slug"],
                provincia=doc["provincia"],
                municipio=doc["municipio"],
                whatsapp_number=doc["whatsapp_number"],
                municipios_envio=doc.get("municipios_envio", []) or [],
                book_count=count,
                foto_tienda_url=doc.get("foto_tienda_url"),
            )
        )
    return stores


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_book(book_id: str, _: UserInDB = Depends(require_admin)):
    db = get_db()
    doc = await db.books.find_one({"_id": book_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")
    await delete_image(doc.get("foto_url", ""), doc.get("cloudinary_public_id"))
    await db.books.delete_one({"_id": book_id})
    return None


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_store(store_id: str, _: UserInDB = Depends(require_admin)):
    db = get_db()
    doc = await db.users.find_one({"_id": store_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada")
    if doc.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede eliminar un admin")
    await delete_image(
        doc.get("foto_tienda_url", ""),
        doc.get("cloudinary_public_id_tienda"),
    )
    async for book in db.books.find({"owner_id": store_id}):
        await delete_image(book.get("foto_url", ""), book.get("cloudinary_public_id"))
    await db.books.delete_many({"owner_id": store_id})
    await db.users.delete_one({"_id": store_id})
    return None
