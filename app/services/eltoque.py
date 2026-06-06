"""Cliente de la API TRMI de elTOQUE (tasas.eltoque.com)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.config import settings

TRMI_URL = "https://tasas.eltoque.com/v1/trmi"
_CACHE_TTL_SECONDS = 3600

_cache: dict[str, Any] = {"expires_at": 0.0, "data": None}


async def fetch_trmi_raw() -> dict[str, Any]:
    token = settings.eltoque_api_token.strip()
    if not token:
        raise RuntimeError("EL_TOQUE_API_TOKEN no está configurado")

    now = time.time()
    if _cache["data"] is not None and now < _cache["expires_at"]:
        return _cache["data"]

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            TRMI_URL,
            headers={"Authorization": f"Bearer {token}", "accept": "*/*"},
        )
        response.raise_for_status()
        data = response.json()

    _cache["data"] = data
    _cache["expires_at"] = now + _CACHE_TTL_SECONDS
    return data
