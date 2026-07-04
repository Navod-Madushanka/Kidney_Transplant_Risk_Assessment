# app/reference_data/hla_loci.py
"""
Canonical list of HLA loci tracked by this system.
Single source of truth — used both for scoring weights (hla_weights.py)
and for the database-level locus enum (models/enums.py).
"""

HLA_LOCI: list[str] = [
    "DRB1",
    "B",
    "DQB1",
    "C",
    "A",
    "DRB3,4,5",
    "DQA1",
    "DPA1",
    "DPB1",
]