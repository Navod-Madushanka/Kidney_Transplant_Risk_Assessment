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

# T14: "DRB3,4,5" is a stored DB enum value (HLALocusEnum in models/enums.py)
# and a dict/set key throughout this codebase (HLA_LOCUS_WEIGHTS, typing
# dicts) -- the comma stays. But shown to a doctor as-is it reads as a list
# of three separate values rather than one composite locus; the frontend
# already displays "HLA-DRB3/4/5" (clinicalEnums.js) -- this is the backend
# display-string equivalent, for any server-built message that names a
# locus. Not a rename; every stored/lookup use of "DRB3,4,5" is unaffected.
HLA_LOCUS_DISPLAY_LABELS: dict[str, str] = {locus: locus for locus in HLA_LOCI}
HLA_LOCUS_DISPLAY_LABELS["DRB3,4,5"] = "DRB3/4/5"


def hla_locus_display_label(locus: str) -> str:
    return HLA_LOCUS_DISPLAY_LABELS.get(locus, locus)
