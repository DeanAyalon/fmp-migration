from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    auth_token: str
    bucket: str
    solution: str
    fms_container: str

    # Optional — omit when ~/.aws is mounted; AWS CLI reads credentials from the mount.
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_default_region: str | None = None

    @field_validator("auth_token", "bucket", "solution", "fms_container")
    @classmethod
    def required_non_empty(cls, value: str) -> str:
        if not value.strip(): raise ValueError("must not be empty")
        return value


@lru_cache
def get_settings() -> Settings: return Settings()
