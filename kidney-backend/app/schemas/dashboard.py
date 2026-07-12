# app/schemas/dashboard.py
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.enums import BloodType


class LatestReportSummary(BaseModel):
    """Summary of a patient's most recent match report, embedded in
    PatientWithLatestReport. risk_tier is None for halted reports (ABO fail
    or DSA trigger halts the pipeline before HLA scoring ever runs), and for
    completed reports it's derived from the stored hla_scoring_result JSON
    rather than a dedicated column, since MatchReport doesn't persist
    risk_tier directly today.
    """

    id: uuid.UUID
    overall_status: str
    risk_tier: Optional[str] = None
    created_at: datetime


class PatientWithLatestReport(BaseModel):
    id: uuid.UUID
    full_name: str
    blood_type: BloodType
    nic_number: Optional[str] = None
    latest_report: Optional[LatestReportSummary] = None


class RecentReportSummary(BaseModel):
    """One row for the dashboard's 'Recent reports' list — patient/donor
    names are denormalized here so the frontend doesn't need a second round
    trip per row.
    """

    id: uuid.UUID
    patient_id: uuid.UUID
    patient_full_name: str
    donor_id: uuid.UUID
    donor_full_name: str
    overall_status: str
    risk_tier: Optional[str] = None
    created_at: datetime