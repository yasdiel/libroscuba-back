"""Slug URL para tiendas públicas (único, legible)."""

import re
import unicodedata
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "login",
        "publicar",
        "perfil",
        "terminos",
        "tienda",
        "tiendas",
        "auth",
        "books",
        "users",
    }
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def slugify_tienda(nombre: str) -> str:
    s = unicodedata.normalize("NFD", nombre.strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "tienda"
    return s[:80]


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


async def nombre_tienda_taken(
    db: AsyncIOMotorDatabase,
    nombre: str,
    *,
    exclude_user_id: Optional[str] = None,
) -> bool:
    name = nombre.strip()
    if not name:
        return False
    query: dict = {"nombre_tienda": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if exclude_user_id:
        query["_id"] = {"$ne": exclude_user_id}
    return await db.users.find_one(query, {"_id": 1}) is not None


async def slug_taken(
    db: AsyncIOMotorDatabase,
    slug: str,
    *,
    exclude_user_id: Optional[str] = None,
) -> bool:
    query: dict = {"tienda_slug": slug}
    if exclude_user_id:
        query["_id"] = {"$ne": exclude_user_id}
    return await db.users.find_one(query, {"_id": 1}) is not None


async def allocate_tienda_slug(
    db: AsyncIOMotorDatabase,
    nombre_tienda: str,
    *,
    exclude_user_id: Optional[str] = None,
) -> str:
    base = slugify_tienda(nombre_tienda)
    if base in RESERVED_SLUGS:
        base = f"{base}-tienda"
    candidate = base
    n = 2
    while await slug_taken(db, candidate, exclude_user_id=exclude_user_id):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


async def find_store_doc(db: AsyncIOMotorDatabase, ref: str) -> Optional[dict]:
    """Busca tienda por slug o, en compatibilidad, por id UUID."""
    key = ref.strip()
    if not key:
        return None
    if is_uuid(key):
        doc = await db.users.find_one({"_id": key})
    else:
        doc = await db.users.find_one({"tienda_slug": key.lower()})
    if not doc:
        return None
    if not doc.get("tienda_slug"):
        slug = await allocate_tienda_slug(db, doc["nombre_tienda"], exclude_user_id=str(doc["_id"]))
        await db.users.update_one({"_id": doc["_id"]}, {"$set": {"tienda_slug": slug}})
        doc["tienda_slug"] = slug
    return doc


async def ensure_tienda_slug_on_user(
    db: AsyncIOMotorDatabase,
    doc: dict,
) -> str:
    slug = doc.get("tienda_slug")
    if slug:
        return slug
    slug = await allocate_tienda_slug(
        db, doc["nombre_tienda"], exclude_user_id=str(doc["_id"])
    )
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"tienda_slug": slug}})
    return slug
