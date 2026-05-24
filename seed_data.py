"""
Reinicia la base de datos con un único usuario administrador.

Desde la carpeta `backend` (usa MONGO_URI y MONGO_DB de `.env`):

    python seed_data.py --reset

Borra todas las colecciones `users` y `books` e inserta solo el admin.
No crea vendedores ni libros de demostración.
"""
import argparse
import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.utils.auth import hash_password
from app.utils.store_slug import allocate_tienda_slug

ADMIN = {
    "password": "admin123",
    "nombre_tienda": "Administración LibrosCuba",
    "whatsapp_number": "+5350000000",
    "provincia": "La Habana",
    "municipio": "Plaza de la Revolución",
    "municipios_envio": [],
}


async def reset_to_admin_only() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db]

    users_deleted = (await db.users.delete_many({})).deleted_count
    books_deleted = (await db.books.delete_many({})).deleted_count
    print(f"Borrados: {users_deleted} usuarios, {books_deleted} libros.")

    now = datetime.now(timezone.utc)
    admin_id = str(uuid4())
    admin_slug = await allocate_tienda_slug(db, ADMIN["nombre_tienda"])
    await db.users.insert_one(
        {
            "_id": admin_id,
            "hashed_password": hash_password(ADMIN["password"]),
            "whatsapp_number": ADMIN["whatsapp_number"],
            "provincia": ADMIN["provincia"],
            "municipio": ADMIN["municipio"],
            "nombre_tienda": ADMIN["nombre_tienda"],
            "tienda_slug": admin_slug,
            "municipios_envio": ADMIN["municipios_envio"],
            "is_admin": True,
            "created_at": now,
        }
    )

    total_users = await db.users.count_documents({})
    total_books = await db.books.count_documents({})
    print(
        f"\nListo. Base `{settings.mongo_db}`: {total_users} usuario(s), {total_books} libro(s)."
    )
    print(f"Admin → WhatsApp: {ADMIN['whatsapp_number']}  Contraseña: {ADMIN['password']}")
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reinicio de LibrosCuba (solo admin)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra users y books e inserta únicamente el usuario admin.",
    )
    args = parser.parse_args()
    if not args.reset:
        print("Usa: python seed_data.py --reset", file=sys.stderr)
        sys.exit(1)
    if not settings.mongo_uri.strip():
        print("MONGO_URI no está definida en .env", file=sys.stderr)
        sys.exit(1)
    asyncio.run(reset_to_admin_only())


if __name__ == "__main__":
    main()
