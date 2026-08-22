# app/services/crossmatch_service.py
"""
Step 6 of the sequential compatibility pipeline. Crossmatch is a same-day
lab result tied to this specific patient/donor pairing rather than a fact
about either person individually, so — unlike HLA typing or antibody
profiles — it isn't stored against the patient or donor record ahead of
time. It's submitted as part of the /compatibility/check request body
(see schemas/match_report.py's CrossmatchInput) and only persisted once a
check actually runs.

Positive crossmatch = the recipient's serum reacts against donor cells =
immunologically incompatible = reject. Negative = no reaction = proceed.
This mapping is standard clinical convention, not a project-specific
judgment call, so unlike Sensitisation/cPRA it didn't need to wait on
doctor confirmation (see the roadmap's Phase 3 open questions).
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class CrossmatchResult:
    is_positive: bool
    is_halted: bool
    t_cell_result: Optional[str] = None
    b_cell_result: Optional[str] = None
    remarks: Optional[str] = None


def check_crossmatch(
    is_positive: bool,
    t_cell_result: Optional[str] = None,
    b_cell_result: Optional[str] = None,
    remarks: Optional[str] = None,
) -> CrossmatchResult:
    return CrossmatchResult(
        is_positive=is_positive,
        is_halted=is_positive,
        t_cell_result=t_cell_result,
        b_cell_result=b_cell_result,
        remarks=remarks,
    )
