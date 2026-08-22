# app/reference_data/dsa_threshold.py
"""
DSA (Donor-Specific Antibody) MFI severity bands for Step 5.

Replaces the old flat DSA_MFI_THRESHOLD = 1000 halt/pass cutoff (fixed
2026-08-08): a single flat threshold either halted transplants over
weak/equivocal antibodies or silently ignored real positives just below the
line, and it duplicated a second, different cutoff
(app/services/dsa_service.DEFAULT_MFI_CUTOFF, 2000) used for cPRA
sensitisation — an antibody at MFI 1500 used to halt the transplant outright
while not even counting toward the patient's sensitisation profile.

DEFAULT_MFI_CUTOFF is intentionally left alone and NOT unified with this
module: it answers a different clinical question (how sensitised is this
patient against the general donor population, for Step 4's cPRA), not
"is this specific donor's antigen a clinically significant DSA" (this
module, Step 5).

Below DSA_MFI_FLOOR an antibody isn't flagged as a DSA at all. At or above
it, severity is graded into three bands — see DSASeverityBand below. Weak
and moderate DSA no longer halt the pipeline outright; they set
DSAResult.requires_review so the pairing proceeds to crossmatch but is
flagged for a clinician's desensitisation-protocol review. Strong DSA still
halts, same as the old gate.

Each MatchReport's dsa_result JSON records the floor/band boundaries that
were actually in force when that report was generated (see
dsa_service.check_dsa), so a later change to these numbers doesn't rewrite
the clinical meaning of past reports.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DSASeverityBand:
    name: str
    min_mfi: float
    max_mfi: float  # inclusive; float("inf") for the top band


DSA_MFI_FLOOR = 1000.0

# Ordered low -> high; the top band's max_mfi is unbounded.
DSA_SEVERITY_BANDS: list[DSASeverityBand] = [
    DSASeverityBand(name="weak", min_mfi=DSA_MFI_FLOOR, max_mfi=1999.999),
    DSASeverityBand(name="moderate", min_mfi=2000.0, max_mfi=4999.999),
    DSASeverityBand(name="strong", min_mfi=5000.0, max_mfi=float("inf")),
]

# Only this band halts the pipeline outright (DSAResult.is_halted). Weak and
# moderate route to DSAResult.requires_review instead — see module docstring.
DSA_HALTING_SEVERITY = "strong"
