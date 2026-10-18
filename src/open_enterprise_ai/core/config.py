"""Centralized application configuration management using pydantic-settings.

Configuration precedence (highest to lowest):
1. OS environment variables
2. .env.{APP_ENV}
3. .env
4. Field defaults in Settings

Note on bootstrap:
APP_ENV is read from the OS environment only (not from .env files),
because its value determines which environment file (.env.{APP_ENV}) is loaded.
Missing environment files are skipped silently without raising errors.
"""

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path anchored to the project root directory (independent of cwd)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

AppEnvType = Literal["local", "development", "test", "staging", "production"]
LogLevelType = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


INSECURE_DEFAULT_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "insecure-dev-secret-change-in-production",
        "change-this-insecure-dev-secret-to-a-secure-random-value",
    }
)
DEFAULT_CONTAINER_SECRETS_DIR: Path = Path("/run/secrets")
MIN_PRODUCTION_SECRET_KEY_LENGTH: int = 16


def _resolve_env_files(app_env: str) -> tuple[Path, ...]:
    """Return absolute paths for base and environment-specific env files."""
    return (
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / f".env.{app_env}",
    )


class Settings(BaseSettings):
    """Application settings model with environment loading and validation."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    # Core configuration fields
    APP_ENV: AppEnvType = "local"
    DEBUG: bool = False
    APP_NAME: str = "open-enterprise-ai"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = Field(8000, ge=1, le=65535)
    LOG_LEVEL: LogLevelType = "INFO"

    # Secret fields (masked in repr, tracebacks, and logs)
    SECRET_KEY: SecretStr = SecretStr(  # audit: ignore[SEC011] -- default development secret key for local non-production bootstrap
        "insecure-dev-secret-change-in-production"
    )

    # OpenAPI Contact Information (optional)
    OPENAPI_CONTACT_NAME: str | None = Field(default=None, max_length=100)
    OPENAPI_CONTACT_EMAIL: str | None = Field(default=None, max_length=100)
    OPENAPI_CONTACT_URL: HttpUrl | None = None

    @field_validator("OPENAPI_CONTACT_NAME", mode="before")
    @classmethod
    def validate_contact_name(cls, v: Any) -> str | None:
        """Strip and normalize empty contact name to None."""
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("OPENAPI_CONTACT_NAME must be a string")  # noqa: TRY004 -- Pydantic requires ValueError for ValidationError wrapping
        v = v.strip()
        return v if v else None

    @field_validator("OPENAPI_CONTACT_EMAIL", mode="before")
    @classmethod
    def validate_contact_email(cls, v: Any) -> str | None:
        """Validate email format and normalize empty email to None."""
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("OPENAPI_CONTACT_EMAIL must be a string")  # noqa: TRY004 -- Pydantic requires ValueError for ValidationError wrapping
        v = v.strip()
        if not v:
            return None
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("OPENAPI_CONTACT_EMAIL must be a valid email address")
        return v

    @field_validator("OPENAPI_CONTACT_URL", mode="before")
    @classmethod
    def validate_contact_url(cls, v: Any) -> Any:
        """Normalize empty URL to None."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def openapi_contact(self) -> dict[str, str] | None:
        """Return OpenAPI contact dictionary if configured."""
        contact: dict[str, str] = {}
        if self.OPENAPI_CONTACT_NAME:
            contact["name"] = self.OPENAPI_CONTACT_NAME
        if self.OPENAPI_CONTACT_EMAIL:
            contact["email"] = self.OPENAPI_CONTACT_EMAIL
        if self.OPENAPI_CONTACT_URL:
            contact["url"] = str(self.OPENAPI_CONTACT_URL)
        return contact or None

    def __init__(self, **values: Any) -> None:
        # Bootstrap: APP_ENV is resolved exclusively from the OS environment
        # to determine which .env file to load, and to prevent .env files
        # from overriding APP_ENV.
        if "APP_ENV" not in values:
            raw_env = (os.getenv("APP_ENV") or "local").strip().lower() or "local"
            values["APP_ENV"] = raw_env

        # Build absolute env file paths anchored to project root
        if "_env_file" not in values:
            app_env = str(values["APP_ENV"])
            values["_env_file"] = _resolve_env_files(app_env)

        # Optional secrets_dir support for containerized mounted secrets
        if "_secrets_dir" not in values:
            secrets_dir = os.getenv("SECRETS_DIR")
            if secrets_dir and Path(secrets_dir).is_dir():
                values["_secrets_dir"] = secrets_dir
            elif DEFAULT_CONTAINER_SECRETS_DIR.is_dir():
                values["_secrets_dir"] = DEFAULT_CONTAINER_SECRETS_DIR

        super().__init__(**values)

    @model_validator(mode="after")
    def validate_production_guardrails(self) -> Settings:
        """Fail fast on insecure configuration in production."""
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must not be True in production environment")
            secret_val = self.SECRET_KEY.get_secret_value().strip()
            if secret_val in INSECURE_DEFAULT_SECRET_KEYS:
                raise ValueError(
                    "SECRET_KEY must be set to a secure, non-default value in production"
                )
            if len(secret_val) < MIN_PRODUCTION_SECRET_KEY_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_KEY_LENGTH} characters in production"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance.

    Call get_settings.cache_clear() to reset during testing.
    """
    return Settings()
