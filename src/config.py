import logging
import sys
from functools import lru_cache

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = (
    "auth_token", "bucket", "solution",
    "fms_container", "fms_admin_user", "fms_admin_password",
    "fm_account", "fm_password",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    auth_token: str
    bucket: str
    solution: str
    
    fms_container: str
    fms_admin_user: str
    fms_admin_password: str
    fm_account: str
    fm_password: str

    # Optional — omit when ~/.aws is mounted; AWS CLI reads credentials from the mount.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_default_region: str | None = None

    @field_validator(*REQUIRED_FIELDS)
    @classmethod
    def required_non_empty(cls, value: str) -> str:
        if not value.strip(): raise ValueError("must not be empty")
        return value


def _log_settings_error(exc: ValidationError) -> None:
    missing: list[str] = []
    empty: list[str] = []

    for err in exc.errors():
        loc = err.get("loc", ())
        if not loc or not isinstance(loc[0], str):
            continue
        env_var = loc[0].upper()
        if err.get("type") == "missing":
            missing.append(env_var)
        elif env_var in {name.upper() for name in REQUIRED_FIELDS}:
            empty.append(env_var)

    for env_var in missing:
        logger.error("Missing environment variable in .env: %s", env_var)
    for env_var in empty:
        logger.error("Empty environment variable in .env: %s", env_var)

    if not missing and not empty:
        logger.error("Invalid configuration in .env")


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        _log_settings_error(exc)
        sys.exit(1)
