from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.data.cuba_locations import is_valid_location, is_valid_municipio
from app.database import get_db
from app.models.user import (
    LoginRequest,
    SendRegisterOtpRequest,
    Token,
    UserCreate,
    UserInDB,
    UserPublic,
)
from app.services.email_otp import (
    email_already_registered,
    normalize_email,
    send_register_email_otp,
    verify_register_email_otp,
)
from app.services.otpcuba_client import OTPCubaError, raise_http_from_otpcuba
from app.utils.auth import (
    create_access_token,
    get_current_user,
    hash_password_async,
    user_from_doc,
    verify_password_async,
)
from app.utils.store_slug import allocate_tienda_slug, nombre_tienda_taken

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register/send-otp", status_code=status.HTTP_204_NO_CONTENT)
async def send_register_otp(payload: SendRegisterOtpRequest):
    email = normalize_email(str(payload.email))
    db = get_db()
    if await email_already_registered(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo. Inicia sesión en su lugar.",
        )
    try:
        await send_register_email_otp(db, email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e)) from e
    except OTPCubaError as e:
        raise_http_from_otpcuba(e)


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

    email = normalize_email(str(payload.email))
    db = get_db()

    try:
        otp_ok = await verify_register_email_otp(db, email, payload.otp)
    except OTPCubaError as e:
        raise_http_from_otpcuba(e)
    if not otp_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código incorrecto o expirado. Solicita uno nuevo.",
        )

    phone = payload.whatsapp_number
    existing_phone = await db.users.find_one({"whatsapp_number": phone})
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este número. Inicia sesión en su lugar.",
        )
    if await email_already_registered(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con este correo. Inicia sesión en su lugar.",
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
        "email": email,
        "hashed_password": hashed,
        "whatsapp_number": phone,
        "provincia": payload.provincia,
        "municipio": payload.municipio,
        "nombre_tienda": payload.nombre_tienda.strip(),
        "tienda_slug": tienda_slug,
        "municipios_envio": payload.municipios_envio,
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
    token = create_access_token(str(doc["_id"]))
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(current: UserInDB = Depends(get_current_user)):
    return UserPublic(
        id=current.id,
        email=current.email,
        whatsapp_number=current.whatsapp_number,
        provincia=current.provincia,
        municipio=current.municipio,
        nombre_tienda=current.nombre_tienda,
        tienda_slug=current.tienda_slug,
        municipios_envio=current.municipios_envio,
        is_admin=current.is_admin,
        foto_tienda_url=current.foto_tienda_url,
    )
