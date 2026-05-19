from fastapi import APIRouter, HTTPException, Query, status

from app.data.cuba_locations import (
    CUBA_LOCATIONS,
    PROVINCES,
    TOTAL_MUNICIPIOS,
    get_municipios,
    is_valid_location,
)

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get("")
async def get_locations():
    """Provincias y municipios de Cuba (168 municipios)."""
    return {
        "provincias": PROVINCES,
        "municipios_por_provincia": CUBA_LOCATIONS,
        "total_municipios": TOTAL_MUNICIPIOS,
    }


@router.get("/provincias")
async def get_provinces():
    return {"provincias": PROVINCES, "total": len(PROVINCES)}


@router.get("/municipios")
async def get_municipalities(provincia: str = Query(..., description="Nombre de la provincia")):
    municipios = get_municipios(provincia)
    if not municipios:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provincia no encontrada: {provincia}",
        )
    return {"provincia": provincia, "municipios": municipios, "total": len(municipios)}


@router.get("/validate")
async def validate_location(
    provincia: str = Query(...),
    municipio: str = Query(...),
):
    valid = is_valid_location(provincia, municipio)
    return {"valid": valid, "provincia": provincia, "municipio": municipio}
