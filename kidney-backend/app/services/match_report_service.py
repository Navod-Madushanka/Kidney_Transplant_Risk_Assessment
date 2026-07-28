# app/services/match_report_service.py
import uuid
from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match_report import MatchReport
from app.services.match_pipeline import MatchPipelineResult


def _to_json(value: Optional[object]) -> Optional[dict]:
    if value is None:
        return None
    return asdict(value)


async def create_match_report(
    db: AsyncSession,
    patient_id: uuid.UUID,
    donor_id: uuid.UUID,
    pipeline_result: MatchPipelineResult,
) -> MatchReport:
    report = MatchReport(
        patient_id=patient_id,
        donor_id=donor_id,
        overall_status=pipeline_result.overall_status,
        abo_result=asdict(pipeline_result.abo_result),
        sensitization_result=_to_json(pipeline_result.sensitization_result),
        dsa_result=_to_json(pipeline_result.dsa_result),
        hla_scoring_result=_to_json(pipeline_result.hla_scoring_result),
        cpra_result=_to_json(pipeline_result.cpra_result),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return report


async def get_match_report_by_id(
    db: AsyncSession, report_id: uuid.UUID
) -> Optional[MatchReport]:
    result = await db.execute(select(MatchReport).where(MatchReport.id == report_id))
    return result.scalar_one_or_none()


async def get_reports_for_patient(
    db: AsyncSession, patient_id: uuid.UUID
) -> list[MatchReport]:
    result = await db.execute(
        select(MatchReport)
        .where(MatchReport.patient_id == patient_id)
        .order_by(MatchReport.created_at.desc())
    )
    return list(result.scalars().all())
