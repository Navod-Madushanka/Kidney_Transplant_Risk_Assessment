# app/api/donors.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.donor import DonorCreate, DonorResponse
from app.services.donor_service import create_donor, get_donor_by_id_for_doctor

router = APIRouter(prefix="/donors", tags=["donors"])


@router.post("", response_model=DonorResponse, status_code=status.HTTP_201_CREATED)
async def create_donor_endpoint(
    payload: DonorCreate,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    donor = await create_donor(db, current_doctor.id, payload)
    return DonorResponse.model_validate(donor)


@router.get("/{donor_id}", response_model=DonorResponse)
async def get_donor_endpoint(
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)

    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    return DonorResponse.model_validate(donor)