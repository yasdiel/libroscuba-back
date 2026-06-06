from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.currency import BASE_CURRENCY, DEFAULT_ACCEPTED
from app.services.media_url import validate_image_url, validate_optional_image_url


class EstadoLibro(str, Enum):
    nuevo = "nuevo"
    usado = "usado"


class BookBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    autor: str = Field(..., min_length=1, max_length=120)
    precio: float = Field(..., gt=0)
    foto_url: str = Field(..., max_length=2048)
    descripcion: Optional[str] = Field(None, max_length=2000)
    estado: EstadoLibro
    provincia: str
    municipio: str


class BookCurrencyMixin(BaseModel):
    moneda: str = Field(default=BASE_CURRENCY, min_length=3, max_length=8)
    monedas_aceptadas: list[str] = Field(default_factory=lambda: list(DEFAULT_ACCEPTED))

    @field_validator("moneda", mode="before")
    @classmethod
    def normalize_moneda(cls, v: object) -> str:
        return str(v or BASE_CURRENCY).strip().upper()

    @field_validator("monedas_aceptadas", mode="before")
    @classmethod
    def normalize_monedas(cls, v: object) -> list[str]:
        if not v:
            return list(DEFAULT_ACCEPTED)
        cleaned: list[str] = []
        for item in v:
            code = str(item).strip().upper()
            if code and code not in cleaned:
                cleaned.append(code)
        return cleaned or list(DEFAULT_ACCEPTED)


class CartSyncBody(BaseModel):
    book_ids: list[str] = Field(default_factory=list, max_length=100)


class BookCreate(BookBase, BookCurrencyMixin):
    @field_validator("foto_url", mode="before")
    @classmethod
    def check_foto_url(cls, v: object) -> str:
        return validate_image_url(str(v), required=True)


class BookUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    autor: Optional[str] = Field(None, min_length=1, max_length=120)
    precio: Optional[float] = Field(None, gt=0)
    foto_url: Optional[str] = Field(None, max_length=2048)
    descripcion: Optional[str] = Field(None, max_length=2000)
    estado: Optional[EstadoLibro] = None
    provincia: Optional[str] = None
    municipio: Optional[str] = None
    moneda: Optional[str] = Field(None, min_length=3, max_length=8)
    monedas_aceptadas: Optional[list[str]] = None

    @field_validator("foto_url", mode="before")
    @classmethod
    def check_foto_url(cls, v: object) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_image_url(str(v), required=True)

    @field_validator("moneda", mode="before")
    @classmethod
    def normalize_moneda(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return str(v).strip().upper()

    @field_validator("monedas_aceptadas", mode="before")
    @classmethod
    def normalize_monedas(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        cleaned: list[str] = []
        for item in v:
            code = str(item).strip().upper()
            if code and code not in cleaned:
                cleaned.append(code)
        return cleaned or list(DEFAULT_ACCEPTED)


class BookInDB(BookBase, BookCurrencyMixin):
    id: str
    owner_id: str
    fecha_creacion: datetime
    cloudinary_public_id: Optional[str] = None


class BookPublic(BookBase, BookCurrencyMixin):
    id: str
    owner_id: str
    fecha_creacion: datetime
    vendedor_nombre: Optional[str] = None
    vendedor_whatsapp: Optional[str] = None
    vendedor_foto_tienda_url: Optional[str] = None
    vendedor_tienda_slug: Optional[str] = None
    vendedor_municipios_envio: list[str] = Field(default_factory=list)


class BookListPublic(BaseModel):
    """Listados: sin descripción para respuestas livianas."""

    id: str
    owner_id: str
    titulo: str
    autor: str
    precio: float
    moneda: str = BASE_CURRENCY
    monedas_aceptadas: list[str] = Field(default_factory=lambda: list(DEFAULT_ACCEPTED))
    foto_url: str
    estado: EstadoLibro
    provincia: str
    municipio: str
    fecha_creacion: datetime
    vendedor_nombre: Optional[str] = None
    vendedor_whatsapp: Optional[str] = None
    vendedor_foto_tienda_url: Optional[str] = None
    vendedor_tienda_slug: Optional[str] = None
    vendedor_municipios_envio: list[str] = Field(default_factory=list)


class BookWithOwner(BookPublic):
    owner_whatsapp: Optional[str] = None
