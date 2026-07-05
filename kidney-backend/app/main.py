# app/main.py
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.api.patients import router as patients_router
from app.api.donors import router as donors_router

app = FastAPI(title="Kidney Transplant Compatibility System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(donors_router)

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


@app.get("/auth/me")
async def read_current_user(current_doctor: Doctor = Depends(get_current_user)):
    return {
        "id": str(current_doctor.id),
        "email": current_doctor.email,
        "full_name": current_doctor.full_name,
        "hospital_id": str(current_doctor.hospital_id),
    }