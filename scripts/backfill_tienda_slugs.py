"""
Asigna tienda_slug a usuarios que aún no lo tienen.

    cd backend
    python scripts/backfill_tienda_slugs.py
"""
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.utils.store_slug import ensure_tienda_slug_on_user


async def main() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    n = 0
    async for doc in db.users.find({"tienda_slug": {"$exists": False}}):
        await ensure_tienda_slug_on_user(db, doc)
        n += 1
    async for doc in db.users.find({"tienda_slug": None}):
        await ensure_tienda_slug_on_user(db, doc)
        n += 1
    async for doc in db.users.find({"tienda_slug": ""}):
        await ensure_tienda_slug_on_user(db, doc)
        n += 1
    print(f"Listo. Slugs asignados o verificados para hasta {n} usuario(s).")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
