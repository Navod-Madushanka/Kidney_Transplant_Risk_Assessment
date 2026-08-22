# app/schemas/_validators.py
"""Field validators shared across multiple schemas."""


def normalize_nic(value: str | None) -> str | None:
    """Uppercase a trailing old-format NIC letter ("v"/"V") so hand entry
    and OCR output converge on one case for the same person -- the active-
    row uniqueness indexes (ix_donors_nic_number_active_unique,
    uq_patients_doctor_id_nic_number_active) are exact-match and
    case-sensitive, so "912345678v" and "912345678V" would otherwise be
    treated as two different people.

    Deliberately does NOT attempt old-format-to-new-format conversion --
    that needs the birth year and a day-of-year offset, and getting it
    wrong would silently merge two different people's records.
    """
    if value is None:
        return value
    if value.endswith("v") or value.endswith("V"):
        return value[:-1] + "V"
    return value
