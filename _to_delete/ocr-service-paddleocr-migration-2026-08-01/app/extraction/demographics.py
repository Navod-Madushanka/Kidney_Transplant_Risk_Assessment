import re
from typing import Optional

from app.extraction.geometry import box_center_y, box_left_x

COLUMN_SPLIT_X = 550
ROW_TOLERANCE_PX = 15

# Different hospital branches phrase the same field differently.
# Ordered longest-first per field so more specific labels are preferred
# when checking a combined "Label: Value" string.
FIELD_LABEL_VARIANTS: dict[str, list[str]] = {
    "full_name": ["Name of the Patient", "Name of the Donor", "Name"],
    "nic_number": ["National Identity Card", "NIC"],
    "date_of_birth": ["Date of Birth", "DOB"],
    "blood_type": ["Blood Type", "Blood Group"],
    "hla_ref_no": ["HLA Ref No", "Laboratory Reference"],
}


def _same_row(box_a: list[int], box_b: list[int]) -> bool:
    return abs(box_center_y(box_a) - box_center_y(box_b)) <= ROW_TOLERANCE_PX


def _build_combined_pattern(variants: list[str]) -> re.Pattern:
    """
    Builds one regex matching ANY of a field's label variants, followed
    by an optional colon and the value. E.g. for full_name:
    matches "Name: X", "Name of the Patient: X", or "Name of the Donor: X".
    """
    escaped = [re.escape(v) for v in variants]
    alternation = "|".join(escaped)
    return re.compile(rf"(?:{alternation})\s*:\s*(.+)")


# Pre-compile once at import time, not per-request.
COMBINED_PATTERNS = {field: _build_combined_pattern(variants) for field, variants in FIELD_LABEL_VARIANTS.items()}


def extract_demographics(texts: list[str], boxes: list[list[int]]) -> dict:
    patient = {"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}
    donor = {"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}

    for i, text in enumerate(texts):
        box = boxes[i]
        target = patient if box_left_x(box) < COLUMN_SPLIT_X else donor
        stripped = text.strip()

        # --- Pattern A: label and value combined in one string ---
        matched_combined = False
        for field, pattern in COMBINED_PATTERNS.items():
            match = pattern.search(text)
            if match:
                target[field] = match.group(1).strip()
                matched_combined = True
                break  # a single text box only ever represents one field

        if matched_combined:
            continue

        # --- Pattern B: this box IS just a label, value lives in a separate box, same row ---
        for field, variants in FIELD_LABEL_VARIANTS.items():
            if stripped in variants:
                value = _find_value_in_same_row(texts, boxes, i)
                if value:
                    target[field] = value.lstrip(":").strip()
                break

    return {"patient_details": patient, "donor_details": donor}


def _find_value_in_same_row(
    texts: list[str], boxes: list[list[int]], label_index: int
) -> Optional[str]:
    label_box = boxes[label_index]
    label_is_patient_side = box_left_x(label_box) < COLUMN_SPLIT_X

    candidates = []
    for j, other_box in enumerate(boxes):
        if j == label_index:
            continue

        other_is_patient_side = box_left_x(other_box) < COLUMN_SPLIT_X
        if other_is_patient_side != label_is_patient_side:
            continue  # don't cross into the other column

        if _same_row(label_box, other_box) and box_left_x(other_box) > box_left_x(label_box):
            candidates.append((box_left_x(other_box), texts[j]))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0])
    return " ".join(text for _, text in candidates)