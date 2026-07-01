# app/main.py
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

app = FastAPI(title="Kidney Transplant Compatibility System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"status": "healthy", "message": "Backend is running!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
async def health_check_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    value = result.scalar()
    return {"status": "ok", "result": value}