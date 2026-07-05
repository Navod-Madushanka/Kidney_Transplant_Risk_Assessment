# app/services/match_pipeline.py
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.donor import Donor
from app.models.patient import Patient
from app.services.abo_service import ABOResult, check_abo_compatibility
from app.services.antibody_profile_service import (
    get_patient_antibody_profiles,
    get_patient_sensitized_antigens,
)
from app.services.cpra_service import CPRAResult, calculate_cpra
from app.services.dsa_service import DEFAULT_MFI_CUTOFF, DSAResult, PatientAntibody, check_dsa
from app.services.hla_scoring_service import HLAScoringResult, calculate_hla_risk_score
from app.services.hla_typing_service import (
    get_donor_hla_typing_dict,
    get_patient_hla_typing_dict,
    get_population_hla_profiles,
)
from app.services.risk_tier_service import get_risk_tier
from app.services.sensitization_event_service import get_patient_sensitization_event_types
from app.services.sensitization_service import SensitizationResult, calculate_sensitization_score


@dataclass
class MatchPipelineResult:
    overall_status: str
    abo_result: ABOResult
    sensitization_result: Optional[SensitizationResult] = None
    dsa_result: Optional[DSAResult] = None
    hla_scoring_result: Optional[HLAScoringResult] = None
    risk_tier: Optional[str] = None
    cpra_result: Optional[CPRAResult] = None


async def run_match_pipeline(
    db: AsyncSession, patient: Patient, donor: Donor
) -> MatchPipelineResult:
    abo_result = check_abo_compatibility(
        patient.blood_type.value, donor.blood_type.value
    )

    if not abo_result.is_compatible:
        return MatchPipelineResult(
            overall_status="halted_abo_fail",
            abo_result=abo_result,
        )

    event_types = await get_patient_sensitization_event_types(db, patient.id)
    sensitization_result = calculate_sensitization_score(
        event_types=event_types, base_mfi_cutoff=DEFAULT_MFI_CUTOFF
    )

    antibody_rows = await get_patient_antibody_profiles(db, patient.id)
    patient_antibodies = [
        PatientAntibody(antigen=row.antigen, mfi=float(row.mfi))
        for row in antibody_rows
    ]

    donor_hla_typing = await get_donor_hla_typing_dict(db, donor.id)
    donor_hla_antigens = [
        allele for alleles in donor_hla_typing.values() for allele in alleles
    ]

    dsa_result = check_dsa(
        patient_antibodies=patient_antibodies,
        donor_hla_antigens=donor_hla_antigens,
        mfi_cutoff_value=sensitization_result.adjusted_mfi_cutoff,
    )

    if dsa_result.is_halted:
        return MatchPipelineResult(
            overall_status="halted_dsa_trigger",
            abo_result=abo_result,
            sensitization_result=sensitization_result,
            dsa_result=dsa_result,
        )

    patient_hla_typing = await get_patient_hla_typing_dict(db, patient.id)
    hla_scoring_result = calculate_hla_risk_score(patient_hla_typing, donor_hla_typing)
    risk_tier = get_risk_tier(hla_scoring_result.total_score)

    sensitized_antigens = await get_patient_sensitized_antigens(
        db, patient.id, DEFAULT_MFI_CUTOFF
    )
    population_profiles = await get_population_hla_profiles(db)
    cpra_result = calculate_cpra(
        sensitized_antigens=sensitized_antigens,
        population_profiles=population_profiles,
    )

    return MatchPipelineResult(
        overall_status="completed",
        abo_result=abo_result,
        sensitization_result=sensitization_result,
        dsa_result=dsa_result,
        hla_scoring_result=hla_scoring_result,
        risk_tier=risk_tier,
        cpra_result=cpra_result,
    )