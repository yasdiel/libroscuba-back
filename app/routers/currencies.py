from fastapi import APIRouter, HTTPException, status

from app.services.currency import build_currencies_payload, convert_amount, get_rates_cup_per_unit
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/currencies", tags=["currencies"])


class ConvertRequest(BaseModel):
    amount: float = Field(..., gt=0)
    from_currency: str = Field(..., min_length=3, max_length=8)
    to_currency: str = Field(..., min_length=3, max_length=8)


@router.get("")
async def list_currencies():
    try:
        return await build_currencies_payload()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudieron obtener las tasas de elTOQUE",
        ) from exc


@router.post("/convert")
async def convert_currency(payload: ConvertRequest):
    try:
        rates = await get_rates_cup_per_unit()
        result = convert_amount(
            payload.amount,
            payload.from_currency,
            payload.to_currency,
            rates,
        )
        return {
            "amount": payload.amount,
            "from_currency": payload.from_currency.upper(),
            "to_currency": payload.to_currency.upper(),
            "converted": round(result, 2),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
