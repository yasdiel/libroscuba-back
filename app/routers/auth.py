from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.data.cuba_locations import is_valid_location, is_valid_municipio
from app.services.currency import available_currency_codes, normalize_monedas, validate_book_currencies
from app.database import get_db
from app.models.user import LoginRequest, Token, UserCreate, UserInDB, UserPublic
from app.utils.auth import (
    create_access_token,
    get_current_user,
    hash_password_async,
    user_from_doc,
    verify_password_async,
)
from app.utils.store_slug import allocate_tienda_slug, nombre_tienda_taken

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate):
    if not payload.accepted_terms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes aceptar los términos y condiciones",
        )
    if not is_valid_location(payload.provincia, payload.municipio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provincia o municipio inválido",
        )
    invalid_envio = [m for m in payload.municipios_envio if not is_valid_municipio(m)]
    if invalid_envio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Municipios de envío inválidos: {', '.join(invalid_envio)}",
        )

    available = await available_currency_codes()
    monedas_aceptadas = normalize_monedas(payload.monedas_aceptadas, available=available)

    db = get_db()
    phone = payload.whatsapp_number
    existing_phone = await db.users.find_one({"whatsapp_number": phone})
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este número. Inicia sesión en su lugar.",
        )
    if await nombre_tienda_taken(db, payload.nombre_tienda):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una tienda con ese nombre. Elige otro nombre.",
        )

    tienda_slug = await allocate_tienda_slug(db, payload.nombre_tienda)
    user_id = str(uuid4())
    hashed = await hash_password_async(payload.password)
    doc = {
        "_id": user_id,
        "hashed_password": hashed,
        "whatsapp_number": phone,
        "provincia": payload.provincia,
        "municipio": payload.municipio,
        "nombre_tienda": payload.nombre_tienda.strip(),
        "tienda_slug": tienda_slug,
        "municipios_envio": payload.municipios_envio,
        "monedas_aceptadas": monedas_aceptadas,
        "is_admin": False,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id)
    return Token(access_token=token)


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest):
    db = get_db()
    doc = await db.users.find_one({"whatsapp_number": payload.whatsapp_number})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe una cuenta con este número. Regístrate primero.",
        )
    if not await verify_password_async(payload.password, doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña incorrecta",
        )
    if doc.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu cuenta está suspendida. Contacta al administrador.",
        )
    token = create_access_token(str(doc["_id"]))
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(current: UserInDB = Depends(get_current_user)):
    return UserPublic(
        id=current.id,
        whatsapp_number=current.whatsapp_number,
        provincia=current.provincia,
        municipio=current.municipio,
        nombre_tienda=current.nombre_tienda,
        tienda_slug=current.tienda_slug,
        municipios_envio=current.municipios_envio,
        monedas_aceptadas=current.monedas_aceptadas,
        is_admin=current.is_admin,
        foto_tienda_url=current.foto_tienda_url,
    )
