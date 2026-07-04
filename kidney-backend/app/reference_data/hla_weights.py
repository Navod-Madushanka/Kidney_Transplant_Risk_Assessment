# app/reference_data/hla_weights.py
"""
HLA locus mismatch weights, by threat tier.
Source: slide 7 (tier definitions) and slide 8 (full locus list, worked example).
"""
from app.reference_data.hla_loci import HLA_LOCI

HLA_LOCUS_WEIGHTS: dict[str, float] = {
    "DRB1": 1.50,
    "B": 1.00,
    "DQB1": 0.50,
    "C": 0.50,
    "A": 0.50,
    "DRB3,4,5": 0.25,
    "DQA1": 0.25,
    "DPA1": 0.25,
    "DPB1": 0.25,
}

assert set(HLA_LOCUS_WEIGHTS.keys()) == set(HLA_LOCI), (
    "HLA_LOCUS_WEIGHTS and HLA_LOCI have drifted out of sync"
)