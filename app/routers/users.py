from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.data.cuba_locations import is_valid_location, is_valid_municipio
from app.database import get_db
from app.models.book import BookListPublic
from app.models.user import UserInDB, UserPublic, UserStorePublic, UserUpdate
from app.routers.books import book_list_from_doc
from app.services.books_query import LIST_BOOK_PROJECTION
from app.services.cloudinary_service import delete_image, extract_public_id
from app.services.media_url import optional_image_url_for_response
from app.utils.auth import get_current_user, user_from_doc
from app.utils.store_slug import (
    allocate_tienda_slug,
    ensure_tienda_slug_on_user,
    find_store_doc,
    nombre_tienda_taken,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_to_public(user: UserInDB) -> UserPublic:
    return UserPublic(
        id=user.id,
        whatsapp_number=user.whatsapp_number,
        provincia=user.provincia,
        municipio=user.municipio,
        nombre_tienda=user.nombre_tienda,
        tienda_slug=user.tienda_slug,
        municipios_envio=user.municipios_envio,
        is_admin=user.is_admin,
        foto_tienda_url=optional_image_url_for_response(user.foto_tienda_url),
    )


@router.get("/me", response_model=UserPublic)
async def get_profile(current: UserInDB = Depends(get_current_user)):
    return _user_to_public(current)


@router.put("/me", response_model=UserPublic)
async def update_profile(payload: UserUpdate, current: UserInDB = Depends(get_current_user)):
    db = get_db()
    updates = payload.model_dump(exclude_unset=True)
    prov = updates.get("provincia", current.provincia)
    mun = updates.get("municipio", current.municipio)
    if "provincia" in updates or "municipio" in updates:
        if not is_valid_location(prov, mun):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provincia o municipio inválido",
            )
    if "municipios_envio" in updates and updates["municipios_envio"] is not None:
        invalid = [m for m in updates["municipios_envio"] if not is_valid_municipio(m)]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Municipios de envío inválidos: {', '.join(invalid)}",
            )
    if "whatsapp_number" in updates:
        existing = await db.users.find_one(
            {"whatsapp_number": updates["whatsapp_number"], "_id": {"$ne": current.id}}
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este número ya está en uso",
            )
    if "nombre_tienda" in updates:
        new_name = updates["nombre_tienda"].strip()
        if await nombre_tienda_taken(db, new_name, exclude_user_id=current.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe una tienda con ese nombre. Elige otro nombre.",
            )
        updates["tienda_slug"] = await allocate_tienda_slug(
            db, new_name, exclude_user_id=current.id
        )
    if "foto_tienda_url" in updates:
        new_url = updates["foto_tienda_url"] or None
        updates["foto_tienda_url"] = new_url
        updates["cloudinary_public_id_tienda"] = (
            extract_public_id(new_url) if new_url else None
        )
        doc = await db.users.find_one({"_id": current.id})
        old_url = doc.get("foto_tienda_url") if doc else None
        if old_url and old_url != new_url:
            await delete_image(old_url, doc.get("cloudinary_public_id_tienda"))
    if updates:
        await db.users.update_one({"_id": current.id}, {"$set": updates})
        doc = await db.users.find_one({"_id": current.id})
        current = user_from_doc(doc)
    return _user_to_public(current)


@router.get("/me/books", response_model=list[BookListPublic])
async def my_books(current: UserInDB = Depends(get_current_user)):
    db = get_db()
    cursor = (
        db.books.find({"owner_id": current.id}, LIST_BOOK_PROJECTION)
        .sort("fecha_creacion", -1)
    )
    books = []
    owner_doc = {
        "nombre_tienda": current.nombre_tienda,
        "whatsapp_number": current.whatsapp_number,
        "municipios_envio": current.municipios_envio,
        "foto_tienda_url": current.foto_tienda_url,
        "tienda_slug": current.tienda_slug,
    }
    async for doc in cursor:
        books.append(book_list_from_doc(doc, owner_doc))
    return books


def _store_from_doc(doc: dict, count: int) -> UserStorePublic:
    return UserStorePublic(
        id=str(doc["_id"]),
        nombre_tienda=doc["nombre_tienda"],
        tienda_slug=doc["tienda_slug"],
        provincia=doc["provincia"],
        municipio=doc["municipio"],
        whatsapp_number=doc["whatsapp_number"],
        municipios_envio=doc.get("municipios_envio", []) or [],
        book_count=count,
        foto_tienda_url=optional_image_url_for_response(doc.get("foto_tienda_url")),
    )


@router.get("/stores", response_model=list[UserStorePublic])
async def list_stores():
    db = get_db()
    stores = []
    async for doc in db.users.find({"is_admin": {"$ne": True}, "is_banned": {"$ne": True}}):
        if not doc.get("tienda_slug"):
            await ensure_tienda_slug_on_user(db, doc)
            doc = await db.users.find_one({"_id": doc["_id"]}) or doc
        count = await db.books.count_documents({"owner_id": str(doc["_id"])})
        stores.append(_store_from_doc(doc, count))
    return stores


@router.get("/stores/{store_slug}", response_model=UserStorePublic)
async def get_store(store_slug: str):
    db = get_db()
    doc = await find_store_doc(db, store_slug)
    if not doc or doc.get("is_admin") or doc.get("is_banned"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada")
    owner_id = str(doc["_id"])
    count = await db.books.count_documents({"owner_id": owner_id})
    return _store_from_doc(doc, count)


@router.get("/stores/{store_slug}/books", response_model=list[BookListPublic])
async def get_store_books(store_slug: str, q: Optional[str] = None):
    db = get_db()
    owner = await find_store_doc(db, store_slug)
    if not owner or owner.get("is_admin") or owner.get("is_banned"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada")
    owner_id = str(owner["_id"])
    query: dict = {"owner_id": owner_id}
    if q:
        query["$or"] = [
            {"titulo": {"$regex": q, "$options": "i"}},
            {"autor": {"$regex": q, "$options": "i"}},
        ]
    owner_doc = {
        "nombre_tienda": owner["nombre_tienda"],
        "whatsapp_number": owner["whatsapp_number"],
        "municipios_envio": owner.get("municipios_envio", []) or [],
        "foto_tienda_url": owner.get("foto_tienda_url"),
        "tienda_slug": owner.get("tienda_slug"),
    }
    cursor = db.books.find(query, LIST_BOOK_PROJECTION).sort("fecha_creacion", -1)
    return [book_list_from_doc(doc, owner_doc) async for doc in cursor]
