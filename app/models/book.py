from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EstadoLibro(str, Enum):
    nuevo = "nuevo"
    usado = "usado"


class BookBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=200)
    autor: str = Field(..., min_length=1, max_length=120)
    precio: float = Field(..., gt=0)
    foto_url: str
    descripcion: Optional[str] = Field(None, max_length=2000)
    estado: EstadoLibro
    provincia: str
    municipio: str


class BookCreate(BookBase):
    pass


class BookUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=1, max_length=200)
    autor: Optional[str] = Field(None, min_length=1, max_length=120)
    precio: Optional[float] = Field(None, gt=0)
    foto_url: Optional[str] = None
    descripcion: Optional[str] = Field(None, max_length=2000)
    estado: Optional[EstadoLibro] = None
    provincia: Optional[str] = None
    municipio: Optional[str] = None


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
    vendedor_municipios_envio: list[str] = Field(default_factory=list)


class BookWithOwner(BookPublic):
    owner_whatsapp: Optional[str] = None
