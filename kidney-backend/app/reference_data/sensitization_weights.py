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

# How much to reduce the DSA MFI cutoff per point of sensitization score.
# Decided formula: cutoff -= sensitization_score * SENSITIZATION_CUTOFF_REDUCTION_FACTOR
SENSITIZATION_CUTOFF_REDUCTION_FACTOR = 100.0
