"""Filtros y lectura paginada de libros (find + batch de tiendas, sin agregación)."""

from typing import Any, Callable, Optional, TypeVar

from motor.motor_asyncio import AsyncIOMotorDatabase

T = TypeVar("T")


def _merge_match(*parts: dict[str, Any]) -> dict[str, Any]:
    filtered = [p for p in parts if p]
    if not filtered:
        return {}
    if len(filtered) == 1:
        return filtered[0]
    return {"$and": filtered}


async def owner_ids_for_location(
    db: AsyncIOMotorDatabase,
    provincia: Optional[str],
    municipio: Optional[str],
) -> Optional[list[str]]:
    """Tiendas cuyos datos de ubicación/envío coinciden con el filtro."""
    if not provincia and not municipio:
        return None
    clauses: list[dict[str, Any]] = []
    if provincia:
        clauses.append({"provincia": provincia})
    if municipio:
        clauses.append(
            {
                "$or": [
                    {"municipio": municipio},
                    {"municipios_envio": municipio},
                ]
            }
        )
    query = clauses[0] if len(clauses) == 1 else {"$and": clauses}
    return [doc["_id"] async for doc in db.users.find(query, {"_id": 1})]


def location_book_match(
    provincia: Optional[str],
    municipio: Optional[str],
    owner_ids: Optional[list[str]],
) -> Optional[dict[str, Any]]:
    """Filtro de ubicación aplicado sobre la colección books."""
    if not provincia and not municipio:
        return None
    clauses: list[dict[str, Any]] = []
    ids_clause = {"owner_id": {"$in": owner_ids or []}}

    if provincia:
        prov: list[dict[str, Any]] = [{"provincia": provincia}]
        if owner_ids is not None:
            prov.append(ids_clause)
        clauses.append({"$or": prov} if len(prov) > 1 else prov[0])

    if municipio:
        mun: list[dict[str, Any]] = [{"municipio": municipio}]
        if owner_ids is not None:
            mun.append(ids_clause)
        clauses.append({"$or": mun} if len(mun) > 1 else mun[0])

    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def build_book_filter(
    *,
    q: Optional[str],
    provincia: Optional[str],
    municipio: Optional[str],
    owner_ids: Optional[list[str]],
) -> dict[str, Any]:
    match_parts: list[dict[str, Any]] = []
    if q:
        match_parts.append(
            {
                "$or": [
                    {"titulo": {"$regex": q, "$options": "i"}},
                    {"autor": {"$regex": q, "$options": "i"}},
                ]
            }
        )
    loc = location_book_match(provincia, municipio, owner_ids)
    if loc:
        match_parts.append(loc)
    return _merge_match(*match_parts)


async def fetch_books_page(
    db: AsyncIOMotorDatabase,
    book_match: dict[str, Any],
    skip: int,
    limit: int,
    to_public: Callable[[dict[str, Any], Optional[dict[str, Any]]], T],
) -> list[T]:
    """Dos consultas indexadas: libros paginados + tiendas de esa página."""
    query = book_match or {}
    docs = (
        await db.books.find(query)
        .sort("fecha_creacion", -1)
        .skip(skip)
        .limit(limit)
        .to_list(length=limit)
    )
    if not docs:
        return []

    owner_ids_list = list({d["owner_id"] for d in docs})
    owners_by_id: dict[str, dict[str, Any]] = {}
    async for user in db.users.find({"_id": {"$in": owner_ids_list}}):
        owners_by_id[user["_id"]] = user

    return [to_public(doc, owners_by_id.get(doc["owner_id"])) for doc in docs]
