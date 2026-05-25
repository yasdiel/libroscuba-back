import os

from pydantic import Field, model_validator
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

    otp_expire_minutes: int = Field(default=5, validation_alias="OTP_EXPIRE_MINUTES")

    # OTP Cuba — envío y verificación OTP por email (HTTPS, funciona en Render).
    otpcuba_api_key: str = ""
    otpcuba_token_secret: str = ""
    otpcuba_base_url: str = "https://otp.noxcreation.dev"

    @model_validator(mode="after")
    def normalize_otpcuba_settings(self) -> "Settings":
        self.otpcuba_api_key = self.otpcuba_api_key.strip()
        self.otpcuba_token_secret = self.otpcuba_token_secret.strip()
        self.otpcuba_base_url = self.otpcuba_base_url.strip().rstrip("/")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def otpcuba_configured(self) -> bool:
        return bool(self.otpcuba_api_key and self.otpcuba_token_secret)

    @property
    def email_configured(self) -> bool:
        return self.otpcuba_configured

    @property
    def email_provider(self) -> str:
        return "otpcuba" if self.otpcuba_configured else "none"

    def email_missing_env(self) -> list[str]:
        missing: list[str] = []
        if not self.otpcuba_api_key:
            missing.append("OTPCUBA_API_KEY")
        if not self.otpcuba_token_secret:
            missing.append("OTPCUBA_TOKEN_SECRET")
        return missing


settings = Settings()
