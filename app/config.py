import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_path() -> str | None:
    """En Render no cargar .env del repo: solo variables del dashboard."""
    if os.getenv("RENDER"):
        return None
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "libroscuba"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    eltoque_api_token: str = Field(
        default="",
        validation_alias=AliasChoices("EL_TOQUE_API_TOKEN", "ELTOQUE_API_TOKEN"),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
