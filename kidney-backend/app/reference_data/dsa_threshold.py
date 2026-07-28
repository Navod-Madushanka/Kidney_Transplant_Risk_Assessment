# app/reference_data/dsa_threshold.py
"""
DSA (Donor-Specific Antibody) MFI threshold for Step 5.
Replaces the old DEFAULT_MFI_CUTOFF (2000) used in dsa_service.py —
per new spec, the cutoff is now a flat 1000, with no sensitization-based
adjustment (Step 2 sensitization is now its own reject/proceed gate,
not a modifier to this cutoff).
"""

DSA_MFI_THRESHOLD = 1000.0