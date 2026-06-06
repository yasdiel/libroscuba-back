"""Monedas soportadas y conversión usando tasas elTOQUE (TRMI)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.services.eltoque import fetch_trmi_raw

BASE_CURRENCY = "CUP"
DEFAULT_ACCEPTED = [BASE_CURRENCY]

# Códigos de la API elTOQUE → código interno de la app
API_CODE_MAP: dict[str, str] = {
    "USD": "USD",
    "ECU": "EUR",
    "MLC": "MLC",
    "USDT_TRC20": "USDT",
    "BTC": "BTC",
    "TRX": "TRX",
    "CAD": "CAD",
    "MXN": "MXN",
    "BRL": "BRL",
    "CLA": "CLA",
}

CURRENCY_LABELS: dict[str, str] = {
    "CUP": "Peso cubano (CUP)",
    "USD": "Dólar (USD)",
    "EUR": "Euro (EUR)",
    "MLC": "MLC",
    "USDT": "USDT (TRC20)",
    "BTC": "Bitcoin (BTC)",
    "TRX": "TRON (TRX)",
    "CAD": "Dólar canadiense (CAD)",
    "MXN": "Peso mexicano (MXN)",
    "BRL": "Real brasileño (BRL)",
    "CLA": "CLA",
}


def currency_label(code: str) -> str:
    return CURRENCY_LABELS.get(code, code)


def normalize_monedas(values: list[str] | None, *, available: set[str]) -> list[str]:
    if not values:
        return [BASE_CURRENCY]
    cleaned: list[str] = []
    for raw in values:
        code = str(raw).strip().upper()
        if not code or code in cleaned:
            continue
        if code not in available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Moneda no soportada: {code}",
            )
        cleaned.append(code)
    if BASE_CURRENCY not in cleaned:
        cleaned.insert(0, BASE_CURRENCY)
    return cleaned


async def get_rates_cup_per_unit() -> dict[str, float]:
    """Cuántos CUP equivale 1 unidad de cada moneda."""
    rates: dict[str, float] = {BASE_CURRENCY: 1.0}
    raw = await fetch_trmi_raw()
    tasas = raw.get("tasas") or {}
    for api_code, value in tasas.items():
        app_code = API_CODE_MAP.get(str(api_code).upper())
        if not app_code:
            continue
        try:
            rate = float(value)
        except (TypeError, ValueError):
            continue
        if rate > 0:
            rates[app_code] = rate
    return rates


async def available_currency_codes() -> set[str]:
    rates = await get_rates_cup_per_unit()
    return set(rates.keys())


async def build_currencies_payload() -> dict[str, Any]:
    raw = await fetch_trmi_raw()
    rates = await get_rates_cup_per_unit()
    currencies = [
        {
            "code": code,
            "label": currency_label(code),
            "rate_cup": rates[code],
        }
        for code in sorted(rates.keys(), key=lambda c: (c != BASE_CURRENCY, c))
    ]
    return {
        "base": BASE_CURRENCY,
        "date": raw.get("date"),
        "time": f"{raw.get('hour', 0):02d}:{raw.get('minutes', 0):02d}:{raw.get('seconds', 0):02d}",
        "currencies": currencies,
    }


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
    rates: dict[str, float],
) -> float:
    src = from_currency.upper()
    dst = to_currency.upper()
    if src not in rates or dst not in rates:
        raise ValueError("Moneda desconocida")
    if src == dst:
        return amount
    cup = amount if src == BASE_CURRENCY else amount * rates[src]
    return cup if dst == BASE_CURRENCY else cup / rates[dst]


async def validate_book_currencies(
    *,
    moneda: str,
    monedas_aceptadas: list[str] | None,
    owner_monedas: list[str] | None,
) -> tuple[str, list[str]]:
    available = await available_currency_codes()
    owner_list = normalize_monedas(owner_monedas, available=available)
    accepted = normalize_monedas(
        monedas_aceptadas if monedas_aceptadas is not None else owner_list,
        available=available,
    )
    for code in accepted:
        if code not in owner_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tu tienda no acepta pagos en {code}",
            )
    price_currency = (moneda or BASE_CURRENCY).strip().upper()
    if price_currency not in available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Moneda de precio no soportada: {price_currency}",
        )
    if price_currency not in accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La moneda del precio debe estar entre las monedas aceptadas",
        )
    return price_currency, accepted


def monedas_from_doc(doc: dict | None) -> list[str]:
    if not doc:
        return list(DEFAULT_ACCEPTED)
    raw = doc.get("monedas_aceptadas")
    if isinstance(raw, list) and raw:
        return [str(c).upper() for c in raw]
    return list(DEFAULT_ACCEPTED)


def moneda_from_doc(doc: dict) -> str:
    return str(doc.get("moneda") or BASE_CURRENCY).upper()
