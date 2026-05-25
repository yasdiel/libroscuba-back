"""
Validación de móviles cubanos (+53 + 8 dígitos nacionales).

Prefijos válidos tras +53: 50–59 (Cubacel histórico, 5 + 7 dígitos) y 63 (líneas nuevas, 63 + 6 dígitos).
"""

import re

CUBA_PREFIX = "+53"
CUBA_LOCAL_DIGITS = 8

# Móvil nacional: 5 + 7 dígitos → tras +53 los dos primeros son 50–59
_CUBA_MOBILE_LEGACY_PREFIXES = {f"5{d}" for d in range(10)}
# Móvil nuevo Cubacel: 63 + 6 dígitos
_CUBA_MOBILE_NEW_PREFIX = "63"

CUBA_MOBILE_TWO_DIGIT_PREFIXES = frozenset(
    _CUBA_MOBILE_LEGACY_PREFIXES | {_CUBA_MOBILE_NEW_PREFIX}
)

INVALID_MOBILE_PREFIX_MSG = "Inserte un número válido."


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone.strip())


def validate_cuba_mobile_local_digits(digits: str) -> None:
    """Valida los 8 dígitos nacionales (sin +53) para línea móvil cubana."""
    if len(digits) != CUBA_LOCAL_DIGITS or not digits.isdigit():
        raise ValueError(INVALID_MOBILE_PREFIX_MSG)
    prefix = digits[:2]
    if prefix not in CUBA_MOBILE_TWO_DIGIT_PREFIXES:
        raise ValueError(INVALID_MOBILE_PREFIX_MSG)


def normalize_phone(phone: str) -> str:
    """Normaliza a +53 + 8 dígitos y valida prefijo móvil cubano."""
    digits = _digits_only(phone)
    if digits.startswith("53") and len(digits) == 10:
        digits = digits[2:]
    validate_cuba_mobile_local_digits(digits)
    return f"{CUBA_PREFIX}{digits}"


def local_digits(phone: str) -> str:
    """Devuelve los 8 dígitos locales a partir de un número normalizado o parcial."""
    normalized = normalize_phone(phone)
    return normalized[len(CUBA_PREFIX) :]
