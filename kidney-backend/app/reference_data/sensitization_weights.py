# app/reference_data/sensitization_weights.py
"""
Sensitization event scoring weights.
Source: slide 5.
"""

SENSITIZATION_EVENT_WEIGHTS: dict[str, float] = {
    "previous_transplant": 2.0,
    "pregnancy": 1.0,
    "blood_transfusion": 0.5,
}

# Feeds SensitizationResult.adjusted_mfi_cutoff (sensitization_service.py)
# only — informational/reference display on the report's Step 2 card, not
# an input to any real gate. Step 5's DSA check has its own independent
# severity bands (see app/reference_data/dsa_threshold.py) that this factor
# does not adjust.
# Formula: cutoff -= sensitization_score * SENSITIZATION_CUTOFF_REDUCTION_FACTOR
SENSITIZATION_CUTOFF_REDUCTION_FACTOR = 100.0
