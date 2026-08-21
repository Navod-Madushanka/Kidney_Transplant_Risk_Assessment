# app/api/compatibility.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.doctor import Doctor
from app.schemas.compatibility_readiness import CompatibilityReadinessResponse
from app.schemas.match_report import CompatibilityCheckRequest, MatchReportResponse
from app.services.audit_service import create_audit_log
from app.services.compatibility_precondition_service import (
    build_compatibility_readiness,
    compute_hla_mismatch_result,
    unverified_data_reasons,
)
from app.services.donor_service import get_donor_for_compatibility_check
from app.services.match_pipeline import CrossmatchInputData, run_match_pipeline
from app.services.match_report_service import (
    create_match_report,
    get_match_report_by_id,
)
from app.services.patient_service import get_patient_by_id_for_doctor

router = APIRouter(prefix="/compatibility", tags=["compatibility"])


@router.post("/check", response_model=MatchReportResponse, status_code=status.HTTP_201_CREATED)
async def check_compatibility(
    payload: CompatibilityCheckRequest,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    patient = await get_patient_by_id_for_doctor(db, payload.patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    donor = await get_donor_for_compatibility_check(db, payload.donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    # Refuse to run the pipeline at all on OCR-extracted clinical data that
    # hasn't been confirmed by a doctor yet (see Patient/Donor.
    # hla_typing_verified / antibody_profile_verified, set by
    # hla_typing_service/antibody_profile_service whenever a PUT ...
    # /hla-typings or /antibody-profiles call declares ocr_verified=False).
    # A same-shape precondition to the 404 checks above: caught before
    # run_match_pipeline/create_match_report ever run, so an unverified
    # check never produces a MatchReport row at all -- this isn't a clinical
    # result to record, it's a request that shouldn't have been made yet.
    unverified_reasons = unverified_data_reasons(patient, donor)
    if unverified_reasons:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Cannot run compatibility check: "
                f"{', '.join(unverified_reasons)} came from OCR extraction and "
                "hasn't been confirmed by a doctor yet. Review and re-save it "
                "against the source document first."
            ),
        )

    # Same category of precondition as the OCR-verification check above,
    # not something to leave for the pipeline to discover: Step 3
    # (hla_mismatch_service.py) worst-cases any missing A/B/DRB1 locus
    # rather than refusing to run, which is the right behavior for the
    # pipeline itself (see that module's docstring) but the wrong one for
    # THIS endpoint to rely on as its only safeguard. GET
    # /compatibility/readiness already surfaces this same gap as a
    # `missing_hla_*` blocking entry for the wizard's preview panel, but
    # that endpoint is advisory -- anything reaching POST
    # /compatibility/check directly (Swagger, a script, a future client)
    # bypasses it entirely. Hoisted here so the API enforces this itself
    # rather than depending on a caller having checked readiness first.
    mismatch_result = await compute_hla_mismatch_result(db, patient, donor)
    if not mismatch_result.data_completeness:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "msg": (
                    "Cannot run compatibility check: HLA typing is incomplete "
                    f"({', '.join(mismatch_result.missing_inputs)}). Enter the "
                    "missing typing, then re-run the check."
                ),
                "missing_inputs": mismatch_result.missing_inputs,
            },
        )

    crossmatch_input = None
    if payload.crossmatch is not None:
        crossmatch_input = CrossmatchInputData(
            is_positive=payload.crossmatch.is_positive,
            t_cell_result=payload.crossmatch.t_cell_result,
            b_cell_result=payload.crossmatch.b_cell_result,
            remarks=payload.crossmatch.remarks,
        )

    pipeline_result = await run_match_pipeline(
        db, patient, donor, crossmatch_input=crossmatch_input
    )

    # Both writes share this call's transaction (commit=False on each, one
    # db.commit() here) so a failure between them can't leave a match report
    # on record with no audit entry for it -- see create_match_report's and
    # create_audit_log's docstrings.
    report = await create_match_report(
        db, payload.patient_id, payload.donor_id, pipeline_result, commit=False
    )

    is_cross_hospital = donor.doctor_id != current_doctor.id
    await create_audit_log(
        db,
        doctor_id=current_doctor.id,
        action="ran_cross_hospital_compatibility_check"
        if is_cross_hospital
        else "ran_compatibility_check",
        patient_id=payload.patient_id,
        donor_id=payload.donor_id,
        details={
            "match_report_id": str(report.id),
            "overall_status": report.overall_status,
            "cross_hospital": is_cross_hospital,
            "donor_doctor_id": str(donor.doctor_id),
        },
        commit=False,
    )

    # create_match_report already refreshed `report` from its flush, and the
    # session is expire_on_commit=False (see app/db/session.py), so its
    # attributes stay valid after this commit without another refresh.
    await db.commit()

    return MatchReportResponse.model_validate(report)


@router.get("/readiness", response_model=CompatibilityReadinessResponse)
async def get_compatibility_readiness_endpoint(
    patient_id: uuid.UUID,
    donor_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview of what's missing before POST /compatibility/check would run
    on this specific pair -- resolves both records with the exact same
    functions that endpoint uses, so the two can never disagree about
    visibility (a donor this doctor can't see 404s here exactly like it
    would at submission time). See compatibility_precondition_service.py's
    module docstring for the blocking vs. score-gap distinction."""
    patient = await get_patient_by_id_for_doctor(db, patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    donor = await get_donor_for_compatibility_check(db, donor_id, current_doctor.id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donor not found",
        )

    readiness = await build_compatibility_readiness(db, patient, donor)
    return CompatibilityReadinessResponse(
        can_run=readiness.can_run,
        blocking=[gap.__dict__ for gap in readiness.blocking],
        lkdpi_gaps=[gap.__dict__ for gap in readiness.lkdpi_gaps],
        donor_risk_projection_gaps=[gap.__dict__ for gap in readiness.donor_risk_projection_gaps],
        donor_risk_contraindication_gaps=[
            gap.__dict__ for gap in readiness.donor_risk_contraindication_gaps
        ],
    )


@router.get("/reports/{report_id}", response_model=MatchReportResponse)
async def get_report_endpoint(
    report_id: uuid.UUID,
    current_doctor: Doctor = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await get_match_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    patient = await get_patient_by_id_for_doctor(db, report.patient_id, current_doctor.id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return MatchReportResponse.model_validate(report)
