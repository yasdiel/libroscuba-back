from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ReportStatus = Literal["pending", "valid", "invalid"]

REPORT_REASONS = (
    "contenido_inapropiado",
    "no_es_libro_fisico",
    "fraude_estafa",
    "otro",
)


class BookReportCreate(BaseModel):
    reason: str = Field(..., min_length=3, max_length=64)
    details: Optional[str] = Field(None, max_length=500)


class BookReportResolve(BaseModel):
    decision: Literal["valid", "invalid"]
    ban_owner: bool = False


class BookReportPublic(BaseModel):
    book_id: str
    status: ReportStatus
    reason: str
    details: Optional[str] = None
    reporter_id: Optional[str] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None


class AdminReportedBook(BaseModel):
    book_id: str
    report_status: ReportStatus
    reason: str
    details: Optional[str] = None
    reporter_id: Optional[str] = None
    reported_at: datetime
    titulo: str
    autor: str
    precio: float
    foto_url: str
    estado: str
    provincia: str
    municipio: str
    owner_id: str
    owner_nombre_tienda: Optional[str] = None
    owner_whatsapp: Optional[str] = None


class BannedUserPublic(BaseModel):
    id: str
    nombre_tienda: str
    whatsapp_number: str
    provincia: str
    municipio: str
    banned_at: datetime
    ban_reason: Optional[str] = None
    book_count: int = 0
