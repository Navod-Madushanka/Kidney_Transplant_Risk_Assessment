from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Centralized configuration, loaded from environment variables.
    This replaces the duplicated os.environ[...] calls we had scattered
    across main.py and ocr_test.py back in Phase 5.
    """
    ocr_service_api_key: str
    max_upload_size_mb: int = 10  # reasonable ceiling for a phone photo

    class Config:
        env_file = ".env"

settings = Settings()