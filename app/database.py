from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

client: AsyncIOMotorClient | None = None
db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    global client, db
    client = AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    db = client[settings.mongo_db]
    await client.admin.command("ping")
    await _ensure_indexes(db)


async def _ensure_indexes(database: AsyncIOMotorDatabase) -> None:
    """Índices para consultas frecuentes en producción."""
    await database.users.create_index("whatsapp_number", unique=True)
    await database.users.create_index("email", unique=True, sparse=True)
    await database.users.create_index("tienda_slug", unique=True, sparse=True)

    await database.email_otps.create_index("expires_at", expireAfterSeconds=0)
    await database.users.create_index("provincia")
    await database.users.create_index("municipio")
    await database.users.create_index("municipios_envio")

    await database.books.create_index([("fecha_creacion", -1)])
    await database.books.create_index("owner_id")
    await database.books.create_index("provincia")
    await database.books.create_index("municipio")


async def close_db() -> None:
    global client, db
    if client:
        client.close()
    client = None
    db = None


def get_db() -> AsyncIOMotorDatabase:
    if db is None:
        raise RuntimeError("Database not initialized")
    return db
