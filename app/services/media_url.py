"""URLs de imágenes: solo HTTPS remotas (Cloudinary desde el cliente)."""

from typing import Optional

MAX_URL_LEN = 2048


def validate_image_url(url: str, *, required: bool = True) -> str:
    if not isinstance(url, str) or not url.strip():
        if required:
            raise ValueError("La imagen es obligatoria")
        return ""
    u = url.strip()
    if u.startswith("data:"):
        raise ValueError("La imagen debe subirse a Cloudinary, no como archivo embebido")
    if len(u) > MAX_URL_LEN:
        raise ValueError("URL de imagen demasiado larga")
    if not u.startswith("https://"):
        raise ValueError("La URL de la imagen debe ser https://")
    return u


def validate_optional_image_url(url: Optional[str]) -> Optional[str]:
    if url is None or url == "":
        return None
    return validate_image_url(url, required=True)


def image_url_for_response(url: Optional[str]) -> str:
    """En lecturas: nunca devolver base64 legado."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    if u.startswith("data:") or not u.startswith("https://"):
        return ""
    return u[:MAX_URL_LEN]


def optional_image_url_for_response(url: Optional[str]) -> Optional[str]:
    u = image_url_for_response(url)
    return u if u else None
