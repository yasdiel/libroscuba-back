import os

from pydantic import AliasChoices, Field, model_validator
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
    smtp_host: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_HOST", "SMPT_HOST"),
    )
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_USER", "SMPT_USER"),
    )
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_PASSWORD", "SMPT_PASSWORD"),
    )
    smtp_from: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_FROM", "SMPT_FROM"),
    )

    @model_validator(mode="after")
    def normalize_smtp(self) -> "Settings":
        self.smtp_host = self.smtp_host.strip()
        self.smtp_user = self.smtp_user.strip()
        self.smtp_password = self.smtp_password.strip().replace(" ", "")
        self.smtp_from = self.smtp_from.strip()
        if self.smtp_user and not self.smtp_from:
            self.smtp_from = self.smtp_user
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    def smtp_missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.smtp_host:
            missing.append("SMTP_HOST")
        if not self.smtp_user:
            missing.append("SMTP_USER")
        if not self.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.smtp_from:
            missing.append("SMTP_FROM (o deja SMTP_USER y se rellena solo)")
        return missing

    @property
    def smtp_configured(self) -> bool:
        return len(self.smtp_missing_fields()) == 0


settings = Settings()
