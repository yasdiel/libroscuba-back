#!/usr/bin/env python3
"""
Limpia foto_url embebidas en base64 en la colección books (causan respuestas de ~1MB+).

Uso (desde backend/, con MONGO_URI de producción en .env o entorno):
  python scripts/fix_embedded_book_photos.py --dry-run
  python scripts/fix_embedded_book_photos.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar cuántos documentos afectados")
    args = parser.parse_args()

    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    query = {"foto_url": {"$regex": r"^data:image"}}
    count = await db.books.count_documents(query)
    print(f"Libros con foto_url base64: {count}")

    if args.dry_run or count == 0:
        client.close()
        return

    result = await db.books.update_many(
        query,
        {"$set": {"foto_url": ""}, "$unset": {"cloudinary_public_id": ""}},
    )
    print(f"Actualizados: {result.modified_count}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
