# app/api/donors.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.donor import DonorCreate, DonorResponse
from app.schemas.hla_typing import HLATypingEntry
from app.services.donor_service import (
    create_donor,
    get_donor_by_id_for_doctor,
    get_donors_for_doctor,
)
from app.services.hla_typing_service import get_donor_hla_typings, replace_donor_hla_typing

router = APIRouter(prefix="/donors", tags=["donors"])


@router.get("", response_model=list[DonorResponse])
async def list_donors_endpoint(
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all donors belonging to the current doctor."""
    donors = await get_donors_for_doctor(db, current_doctor.id)
    return [DonorResponse.model_validate(d) for d in donors]


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


@router.put("/{donor_id}/hla-typings", status_code=status.HTTP_204_NO_CONTENT)
async def replace_donor_hla_typing_endpoint(
    donor_id: uuid.UUID,
    entries: list[HLATypingEntry],
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    donor = await get_donor_by_id_for_doctor(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    await replace_donor_hla_typing(db, donor_id, entries)


@router.get("/{donor_id}/hla-typings", response_model=list[HLATypingEntry])
async def get_donor_hla_typings_endpoint(
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

    return await get_donor_hla_typings(db, donor_id)
