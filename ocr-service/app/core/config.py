from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Centralized configuration, loaded from environment variables.
    This replaces the duplicated os.environ[...] calls we had scattered
    across main.py and ocr_test.py back in Phase 5.
    """
    ocr_service_api_key: str
    max_upload_size_mb: int = 10  # reasonable ceiling for a phone photo

    # --- LLM extraction backend ---
    # Replaces PaddleOCR as of the OCR -> local vision-LLM migration (see
    # claude/ocr-to-local-llm-migration-plan.md in the project for the full
    # rationale and Phase 1 validation results).
    ollama_base_url: str = "http://localhost:11434"  # docker-compose.yml overrides
                                                       # this to http://ollama:11434
                                                       # for the containerized service;
                                                       # this default is for running
                                                       # ocr-service directly on the
                                                       # host against a local `ollama serve`.
    ollama_model: str = "qwen3-vl:4b-nothink"          # the Modelfile-built non-thinking
                                                       # variant (see docker/ollama-entrypoint.sh).
                                                       # Plain "qwen3-vl:4b" hits a confirmed,
                                                       # currently-open Ollama bug
                                                       # (ollama/ollama#13353) where
                                                       # "think": false is silently ignored.

    # Pydantic V2 style (2026-08-01 -- the class-based Config above was
    # deprecated-since-2.0 and started emitting a warning once Phase 4's
    # test suite actually exercised this import path repeatedly).
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
