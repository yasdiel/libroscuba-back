from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.media_url import validate_optional_image_url
from app.utils.phone import normalize_phone


def _clean_municipios(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    seen: list[str] = []
    for v in values:
        if not isinstance(v, str):
            continue
        name = v.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


class UserBase(BaseModel):
    whatsapp_number: str
    provincia: str = Field(..., min_length=1)
    municipio: str = Field(..., min_length=1)
    nombre_tienda: str = Field(..., min_length=2, max_length=80)
    municipios_envio: list[str] = Field(default_factory=list)

    @field_validator("whatsapp_number", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except ValueError as e:
            raise ValueError(str(e)) from e

    @field_validator("municipios_envio", mode="before")
    @classmethod
    def clean_envio(cls, v: Optional[list[str]]) -> list[str]:
        return _clean_municipios(v)


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=128)
    accepted_terms: bool = False


class UserUpdate(BaseModel):
    whatsapp_number: Optional[str] = None
    provincia: Optional[str] = None
    municipio: Optional[str] = None
    nombre_tienda: Optional[str] = Field(None, min_length=2, max_length=80)
    municipios_envio: Optional[list[str]] = None
    foto_tienda_url: Optional[str] = Field(None, max_length=2048)

    @field_validator("foto_tienda_url", mode="before")
    @classmethod
    def validate_foto_tienda_url(cls, v: Optional[str]) -> Optional[str]:
        return validate_optional_image_url(v)

    @field_validator("whatsapp_number", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            return normalize_phone(v)
        except ValueError as e:
            raise ValueError(str(e)) from e

    @field_validator("municipios_envio", mode="before")
    @classmethod
    def clean_envio(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return _clean_municipios(v)


class UserInDB(UserBase):
    id: str
    hashed_password: str
    is_admin: bool = False
    created_at: datetime
    foto_tienda_url: Optional[str] = None


class UserPublic(BaseModel):
    id: str
    whatsapp_number: str
    provincia: str
    municipio: str
    nombre_tienda: str
    municipios_envio: list[str] = Field(default_factory=list)
    is_admin: bool = False
    foto_tienda_url: Optional[str] = None


class UserStorePublic(BaseModel):
    id: str
    nombre_tienda: str
    provincia: str
    municipio: str
    whatsapp_number: str
    municipios_envio: list[str] = Field(default_factory=list)
    book_count: int = 0
    foto_tienda_url: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    whatsapp_number: str
    password: str = Field(..., min_length=6, max_length=128)

    @field_validator("whatsapp_number", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except ValueError as e:
            raise ValueError(str(e)) from e
