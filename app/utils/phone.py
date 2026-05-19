import re

CUBA_PREFIX = "+53"
CUBA_LOCAL_DIGITS = 8


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone.strip())


def normalize_phone(phone: str) -> str:
    """Normaliza a +53 + 8 dígitos locales (solo enteros)."""
    digits = _digits_only(phone)
    if digits.startswith("53") and len(digits) == 10:
        digits = digits[2:]
    if len(digits) != CUBA_LOCAL_DIGITS or not digits.isdigit():
        raise ValueError(
            f"El teléfono debe tener exactamente {CUBA_LOCAL_DIGITS} dígitos numéricos"
        )
    return f"{CUBA_PREFIX}{digits}"


def local_digits(phone: str) -> str:
    """Devuelve los 8 dígitos locales a partir de un número normalizado o parcial."""
    normalized = normalize_phone(phone)
    return normalized[len(CUBA_PREFIX) :]
