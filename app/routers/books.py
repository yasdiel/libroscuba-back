from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.data.cuba_locations import is_valid_location
from app.database import get_db
from app.models.book import BookCreate, BookInDB, BookListPublic, BookPublic, BookUpdate, CartSyncBody
from app.models.report import BookReportCreate
from app.services.media_url import image_url_for_response, optional_image_url_for_response
from app.models.user import UserInDB
from app.services.book_reports import banned_owner_ids, create_book_report
from app.services.books_query import (
    build_book_filter,
    fetch_books_page,
    owner_ids_for_location,
)
from app.services.cloudinary_service import delete_image, extract_public_id
from app.utils.auth import get_current_user, get_optional_user
from app.utils.store_slug import find_store_doc

router = APIRouter(prefix="/api/books", tags=["books"])


async def _exclude_banned_owners(
    db, book_match: dict
) -> dict:
    banned = await banned_owner_ids(db)
    if not banned:
        return book_match
    clause = {"owner_id": {"$nin": banned}}
    if not book_match:
        return clause
    return {"$and": [book_match, clause]}


def _vendedor_tienda_slug(vendedor: Optional[dict]) -> Optional[str]:
    if not vendedor:
        return None
    slug = vendedor.get("tienda_slug")
    return slug if slug else None


def book_from_doc(doc: dict, vendedor: Optional[dict] = None) -> BookPublic:
    return BookPublic(
        id=str(doc["_id"]),
        owner_id=doc["owner_id"],
        titulo=doc["titulo"],
        autor=doc["autor"],
        precio=doc["precio"],
        foto_url=image_url_for_response(doc.get("foto_url")),
        descripcion=doc.get("descripcion"),
        estado=doc["estado"],
        provincia=doc["provincia"],
        municipio=doc["municipio"],
        fecha_creacion=doc.get("fecha_creacion", datetime.now(timezone.utc)),
        vendedor_nombre=vendedor.get("nombre_tienda") if vendedor else None,
        vendedor_whatsapp=vendedor.get("whatsapp_number") if vendedor else None,
        vendedor_foto_tienda_url=(
            optional_image_url_for_response(vendedor.get("foto_tienda_url")) if vendedor else None
        ),
        vendedor_tienda_slug=_vendedor_tienda_slug(vendedor),
        vendedor_municipios_envio=(vendedor.get("municipios_envio") if vendedor else None) or [],
    )


def book_list_from_doc(doc: dict, vendedor: Optional[dict] = None) -> BookListPublic:
    return BookListPublic(
        id=str(doc["_id"]),
        owner_id=doc["owner_id"],
        titulo=doc["titulo"],
        autor=doc["autor"],
        precio=doc["precio"],
        foto_url=image_url_for_response(doc.get("foto_url")),
        estado=doc["estado"],
        provincia=doc["provincia"],
        municipio=doc["municipio"],
        fecha_creacion=doc.get("fecha_creacion", datetime.now(timezone.utc)),
        vendedor_nombre=vendedor.get("nombre_tienda") if vendedor else None,
        vendedor_whatsapp=vendedor.get("whatsapp_number") if vendedor else None,
        vendedor_foto_tienda_url=(
            optional_image_url_for_response(vendedor.get("foto_tienda_url")) if vendedor else None
        ),
        vendedor_tienda_slug=_vendedor_tienda_slug(vendedor),
        vendedor_municipios_envio=(vendedor.get("municipios_envio") if vendedor else None) or [],
    )


@router.get("", response_model=list[BookListPublic])
async def list_books(
    provincia: Optional[str] = None,
    municipio: Optional[str] = None,
    q: Optional[str] = Query(None, description="Búsqueda por título o autor"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
):
    """Lista libros. El filtro por municipio incluye también las tiendas que
    declararon hacer envíos a ese municipio (campo `municipios_envio` del dueño).
    """
    db = get_db()
    owner_ids = await owner_ids_for_location(db, provincia, municipio)
    book_match = build_book_filter(
        q=q,
        provincia=provincia,
        municipio=municipio,
        owner_ids=owner_ids,
    )
    book_match = await _exclude_banned_owners(db, book_match)
    return await fetch_books_page(db, book_match, skip, limit, book_list_from_doc)


@router.post("/cart-sync", response_model=list[BookListPublic])
async def sync_cart_books(payload: CartSyncBody):
    """Devuelve los libros del carrito que siguen publicados (excluye baneados/eliminados)."""
    if not payload.book_ids:
        return []
    db = get_db()
    banned = await banned_owner_ids(db)
    owner_filter: dict = {}
    if banned:
        owner_filter["owner_id"] = {"$nin": banned}
    books: list[BookListPublic] = []
    async for doc in db.books.find({"_id": {"$in": payload.book_ids}, **owner_filter}):
        owner = await find_store_doc(db, doc["owner_id"])
        books.append(book_list_from_doc(doc, owner))
    order = {bid: i for i, bid in enumerate(payload.book_ids)}
    books.sort(key=lambda b: order.get(b.id, 999))
    return books


@router.get("/{book_id}", response_model=BookPublic)
async def get_book(book_id: str):
    db = get_db()
    doc = await db.books.find_one({"_id": book_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")
    owner = await find_store_doc(db, doc["owner_id"])
    if owner and owner.get("is_banned"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")
    return book_from_doc(doc, owner)


@router.post("/{book_id}/report", status_code=status.HTTP_204_NO_CONTENT)
async def report_book(
    book_id: str,
    payload: BookReportCreate,
    current: UserInDB | None = Depends(get_optional_user),
):
    db = get_db()
    await create_book_report(
        db,
        book_id=book_id,
        reporter_id=current.id if current else None,
        reason=payload.reason,
        details=payload.details,
    )
    return None


@router.post("", response_model=BookPublic, status_code=status.HTTP_201_CREATED)
async def create_book(payload: BookCreate, current: UserInDB = Depends(get_current_user)):
    if not is_valid_location(payload.provincia, payload.municipio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provincia o municipio inválido",
        )
    db = get_db()
    book_id = str(uuid4())
    doc = {
        "_id": book_id,
        "owner_id": current.id,
        "titulo": payload.titulo,
        "autor": payload.autor,
        "precio": payload.precio,
        "foto_url": payload.foto_url,
        "descripcion": payload.descripcion,
        "estado": payload.estado.value if hasattr(payload.estado, "value") else payload.estado,
        "provincia": payload.provincia,
        "municipio": payload.municipio,
        "fecha_creacion": datetime.now(timezone.utc),
        "cloudinary_public_id": extract_public_id(payload.foto_url),
    }
    await db.books.insert_one(doc)
    owner_doc = {
        "nombre_tienda": current.nombre_tienda,
        "whatsapp_number": current.whatsapp_number,
        "municipios_envio": current.municipios_envio,
        "foto_tienda_url": current.foto_tienda_url,
        "tienda_slug": current.tienda_slug,
    }
    return book_from_doc(doc, owner_doc)


@router.put("/{book_id}", response_model=BookPublic)
async def update_book(
    book_id: str, payload: BookUpdate, current: UserInDB = Depends(get_current_user)
):
    db = get_db()
    doc = await db.books.find_one({"_id": book_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")
    if doc["owner_id"] != current.id and not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    updates = payload.model_dump(exclude_unset=True)
    prov = updates.get("provincia", doc.get("provincia"))
    mun = updates.get("municipio", doc.get("municipio"))
    if not is_valid_location(prov, mun):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provincia o municipio inválido",
        )
    if "estado" in updates and updates["estado"] is not None:
        updates["estado"] = updates["estado"].value if hasattr(updates["estado"], "value") else updates["estado"]
    if "foto_url" in updates:
        updates["cloudinary_public_id"] = extract_public_id(updates["foto_url"])
        old_url = doc.get("foto_url")
        if old_url and old_url != updates["foto_url"]:
            await delete_image(old_url, doc.get("cloudinary_public_id"))
    if updates:
        await db.books.update_one({"_id": book_id}, {"$set": updates})
    doc = await db.books.find_one({"_id": book_id})
    owner = await find_store_doc(db, doc["owner_id"])
    return book_from_doc(doc, owner)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(book_id: str, current: UserInDB = Depends(get_current_user)):
    db = get_db()
    doc = await db.books.find_one({"_id": book_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Libro no encontrado")
    if doc["owner_id"] != current.id and not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
    await delete_image(doc.get("foto_url", ""), doc.get("cloudinary_public_id"))
    await db.books.delete_one({"_id": book_id})
    return None
