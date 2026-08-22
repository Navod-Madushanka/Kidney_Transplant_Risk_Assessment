# app/reference_data/abo_compatibility.py

"""
ABO blood group compatibility rules for kidney transplant matching.
Source: slide 2 — OPTN ABO Blood Group Compatibility policy.

Bump ABO_COMPATIBILITY_VERSION any time the table below changes, so a
report's stamped reference_versions (see MatchReport.reference_versions,
app/reference_data/versions.py) keeps meaning exactly what it meant when
that report was generated.
"""

ABO_COMPATIBILITY_VERSION = "optn-abo-policy-v1"

ABO_COMPATIBILITY: dict[str, list[str]] = {
    "O": ["O"],
    "A": ["A", "O"],
    "B": ["B", "O"],
    "AB": ["A", "B", "AB", "O"],
}
