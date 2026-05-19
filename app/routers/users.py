from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.data.cuba_locations import is_valid_location, is_valid_municipio
from app.database import get_db
from app.models.book import BookPublic
from app.models.user import UserInDB, UserPublic, UserStorePublic, UserUpdate
from app.routers.books import book_from_doc
from app.utils.auth import get_current_user, user_from_doc

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_to_public(user: UserInDB) -> UserPublic:
    return UserPublic(
        id=user.id,
        whatsapp_number=user.whatsapp_number,
        provincia=user.provincia,
        municipio=user.municipio,
        nombre_tienda=user.nombre_tienda,
        municipios_envio=user.municipios_envio,
        is_admin=user.is_admin,
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
    if updates:
        await db.users.update_one({"_id": current.id}, {"$set": updates})
        doc = await db.users.find_one({"_id": current.id})
        current = user_from_doc(doc)
    return _user_to_public(current)


@router.get("/me/books", response_model=list[BookPublic])
async def my_books(current: UserInDB = Depends(get_current_user)):
    db = get_db()
    cursor = db.books.find({"owner_id": current.id}).sort("fecha_creacion", -1)
    books = []
    owner_doc = {
        "nombre_tienda": current.nombre_tienda,
        "whatsapp_number": current.whatsapp_number,
        "municipios_envio": current.municipios_envio,
    }
    async for doc in cursor:
        books.append(book_from_doc(doc, owner_doc))
    return books


def _store_from_doc(doc: dict, count: int) -> UserStorePublic:
    return UserStorePublic(
        id=str(doc["_id"]),
        nombre_tienda=doc["nombre_tienda"],
        provincia=doc["provincia"],
        municipio=doc["municipio"],
        whatsapp_number=doc["whatsapp_number"],
        municipios_envio=doc.get("municipios_envio", []) or [],
        book_count=count,
    )


@router.get("/stores", response_model=list[UserStorePublic])
async def list_stores():
    db = get_db()
    stores = []
    async for doc in db.users.find({"is_admin": {"$ne": True}}):
        count = await db.books.count_documents({"owner_id": str(doc["_id"])})
        stores.append(_store_from_doc(doc, count))
    return stores


@router.get("/stores/{store_id}", response_model=UserStorePublic)
async def get_store(store_id: str):
    db = get_db()
    doc = await db.users.find_one({"_id": store_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada")
    count = await db.books.count_documents({"owner_id": store_id})
    return _store_from_doc(doc, count)


@router.get("/stores/{store_id}/books", response_model=list[BookPublic])
async def get_store_books(store_id: str, q: Optional[str] = None):
    db = get_db()
    owner = await db.users.find_one({"_id": store_id})
    if not owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tienda no encontrada")
    query: dict = {"owner_id": store_id}
    if q:
        query["$or"] = [
            {"titulo": {"$regex": q, "$options": "i"}},
            {"autor": {"$regex": q, "$options": "i"}},
        ]
    owner_doc = {
        "nombre_tienda": owner["nombre_tienda"],
        "whatsapp_number": owner["whatsapp_number"],
        "municipios_envio": owner.get("municipios_envio", []) or [],
    }
    cursor = db.books.find(query).sort("fecha_creacion", -1)
    return [book_from_doc(doc, owner_doc) async for doc in cursor]
