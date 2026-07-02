# app/reference_data/hla_weights.py
"""
HLA locus mismatch weights, by threat tier.
Source: slide 7 (tier definitions) and slide 8 (full locus list, worked example).
"""

HLA_LOCUS_WEIGHTS: dict[str, float] = {
    "DRB1": 1.50,   # Critical
    "B": 1.00,      # High
    "DQB1": 0.50,   # Low
    "C": 0.50,      # Low
    "A": 0.50,      # Low
    "DRB3,4,5": 0.25,  # Minimal
    "DQA1": 0.25,      # Minimal
    "DPA1": 0.25,      # Minimal
    "DPB1": 0.25,      # Minimal
}