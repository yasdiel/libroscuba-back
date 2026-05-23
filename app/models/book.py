from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

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


class BookCreate(BookBase):
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

    @field_validator("foto_url", mode="before")
    @classmethod
    def check_foto_url(cls, v: object) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_image_url(str(v), required=True)


class BookInDB(BookBase):
    id: str
    owner_id: str
    fecha_creacion: datetime
    cloudinary_public_id: Optional[str] = None


class BookPublic(BookBase):
    id: str
    owner_id: str
    fecha_creacion: datetime
    vendedor_nombre: Optional[str] = None
    vendedor_whatsapp: Optional[str] = None
    vendedor_foto_tienda_url: Optional[str] = None
    vendedor_municipios_envio: list[str] = Field(default_factory=list)


class BookListPublic(BaseModel):
    """Listados: sin descripción para respuestas livianas."""

    id: str
    owner_id: str
    titulo: str
    autor: str
    precio: float
    foto_url: str
    estado: EstadoLibro
    provincia: str
    municipio: str
    fecha_creacion: datetime
    vendedor_nombre: Optional[str] = None
    vendedor_whatsapp: Optional[str] = None
    vendedor_foto_tienda_url: Optional[str] = None
    vendedor_municipios_envio: list[str] = Field(default_factory=list)


class BookWithOwner(BookPublic):
    owner_whatsapp: Optional[str] = None
