# app/reference_data/abo_compatibility.py

"""
ABO blood type compatibility rules for kidney transplant matching.
Source: slide 2 — OPTN ABO Blood Group Compatibility policy.
"""

ABO_COMPATIBILITY: dict[str, list[str]] = {
    "O": ["O"],
    "A": ["A", "O"],
    "B": ["B", "O"],
    "AB": ["A", "B", "AB", "O"],
}
