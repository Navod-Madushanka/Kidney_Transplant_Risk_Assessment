# app/tests/unit/test_hla_scoring_service.py
from app.services.hla_scoring_service import calculate_hla_risk_score

# This exact patient/donor pair comes from slide 8's worked lab example.
# Expected total: 6.5 pts (High-Moderate Risk). If this ever fails after a
# refactor, something in the scoring logic broke — this is our ground truth.

PATIENT_TYPING = {
    "DRB1": ["03", "04"],
    "B": ["07", "58"],
    "DQB1": ["02", "03"],
    "C": ["03", "15"],
    "A": ["29", "33"],
    "DRB3,4,5": ["DRB3*02", "DRB4*01"],
    "DQA1": ["03", "05"],
    "DPA1": ["01", "01"],
    "DPB1": ["04", "04"],
}

DONOR_TYPING = {
    "DRB1": ["13", "14"],
    "B": ["40", "40"],
    "DQB1": ["05", "06"],
    "C": ["12", "15"],
    "A": ["33", "33"],
    "DRB3,4,5": ["DRB3*01", "DRB3*02"],
    "DQA1": ["01", "01"],
    "DPA1": ["02", "02"],
    "DPB1": ["04", "13"],
}


def test_hla_scoring_matches_lab_worked_example():
    result = calculate_hla_risk_score(PATIENT_TYPING, DONOR_TYPING)
    assert result.total_score == 6.5


def test_hla_scoring_locus_breakdown_drb1():
    result = calculate_hla_risk_score(PATIENT_TYPING, DONOR_TYPING)
    drb1 = next(r for r in result.locus_breakdown if r.locus == "DRB1")
    assert drb1.unique_mismatches == 2
    assert drb1.points == 3.0