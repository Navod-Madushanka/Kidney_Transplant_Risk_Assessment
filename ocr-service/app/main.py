import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router as ocr_router

# Python's root logger defaults to WARNING with no handler attached, so
# app.llm.client's per-request timing logs (INFO level — see
# app/llm/client.py::_log_timing, added in the Phase 1 speed pass) would
# otherwise be silently dropped. Basic stdout config is enough here; this
# runs under uvicorn, whose own process already writes to the container's
# stdout, so `docker compose logs ocr-service` picks this up too.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # No more expensive in-process model load here — that's what this hook
    # used to do for PaddleOCR (app.state.ocr_engine = OCREngine()).
    # Extraction now calls out to a separate Ollama service (see
    # docker-compose.yml) instead, so there's nothing to warm up at
    # startup. Kept as a lifespan context in case a future need (e.g. a
    # startup check that Ollama + the -nothink model are actually reachable
    # before accepting traffic) wants this hook.
    yield

app = FastAPI(title="Kidney Risk OCR Service", lifespan=lifespan)
app.include_router(ocr_router)

@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "ocr-service"}
