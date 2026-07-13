from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.ocr.engine import OCREngine
from app.api.routes import router as ocr_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup — this is where the expensive model load happens
    app.state.ocr_engine = OCREngine()
    yield
    # Code after "yield" would run on shutdown — nothing needed here yet

app = FastAPI(title="Kidney Risk OCR Service", lifespan=lifespan)
app.include_router(ocr_router)

@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "ocr-service"}