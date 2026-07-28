# app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    # Reserved for future use (e.g. caching, rate limiting, session storage).
    # Provisioned in local setup but not read anywhere in the app yet — see
    # the roadmap's Phase 1 note before adding a new use for it.
    redis_url: str
    secret_key: str
    environment: str = "local"

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # OCR service
    ocr_service_url: str = "http://localhost:8001"
    ocr_service_api_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
