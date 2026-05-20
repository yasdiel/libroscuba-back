from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, connect_db
from app.routers import admin, auth, books, locations, upload, users
from app.services.cloudinary_service import configure_cloudinary


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect_db()
    configure_cloudinary()
    yield
    await close_db()


app = FastAPI(
    title="LibrosCuba API",
    description="API para compra y venta de libros físicos en Cuba",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(books.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(locations.router)
app.include_router(upload.router)


@app.get("/api/health")
async def health():
    """Health check de Render: confirma API + Mongo."""
    from app.database import get_db

    db = get_db()
    await db.command("ping")
    return {"status": "ok", "service": "libroscuba", "database": "connected"}


@app.get("/api/ping")
async def ping():
    """Respuesta mínima para calentar el proceso sin tocar Mongo."""
    return {"status": "ok"}
