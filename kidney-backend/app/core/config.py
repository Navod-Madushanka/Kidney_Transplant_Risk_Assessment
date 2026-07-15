# app/core/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
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