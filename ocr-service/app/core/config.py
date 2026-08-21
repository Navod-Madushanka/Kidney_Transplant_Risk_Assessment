from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration, loaded from environment variables.
    This replaces the duplicated os.environ[...] calls we had scattered
    across main.py and ocr_test.py back in Phase 5.
    """
    ocr_service_api_key: str
    # Must stay equal to kidney-backend's Settings.ocr_upload_max_size_mb
    # (see kidney-backend/app/core/config.py) — kidney-backend's spool
    # rejects anything above its own cap before this service ever sees the
    # upload, so a mismatch here just means one of the two caps is dead
    # weight. Raised from 10 to 15 in the Part G bounded-memory pass to
    # match: a 300dpi A4 scan of a bead-specificity chart is legitimately
    # 3-6MB, and rejecting a real report is a clinical workflow failure.
    max_upload_size_mb: int = 15

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
