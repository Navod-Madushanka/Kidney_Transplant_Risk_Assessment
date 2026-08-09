# app/schemas/donor_risk.py
from pydantic import BaseModel


class DonorRiskAssessmentResponse(BaseModel):
    """Mirrors app/services/donor_risk_service.DonorRiskAssessmentResult
    field-for-field. Built via DonorRiskAssessmentResponse(**asdict(result))
    -- not backed by an ORM model, so no from_attributes config, matching
    app/schemas/donor_search.py and exchange.py's plain-BaseModel pattern
    for computed (non-persisted) results."""

    has_sufficient_data_for_projection: bool
    missing_projection_predictors: list[str]
    fifteen_year_risk_percent: float | None
    lifetime_risk_percent: float | None
    relative_risk_multiplier: float | None
    linear_predictor: float | None
    age_band_used: str | None
    race_used_for_scoring: str | None

    has_sufficient_data_for_contraindication_screen: bool
    missing_contraindication_predictors: list[str]
    contraindications: list[str]
    has_any_contraindication: bool
    contraindication_criteria_not_assessed: list[str]

    diabetes_review_flag: bool | None
    family_history_flag: bool | None

    population_validated: bool
    general_disclaimer: str
    race_extrapolation_disclaimer: str | None
    source_citation: str
    values_outside_model_range: list[str]
