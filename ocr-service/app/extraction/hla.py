# app/extraction/hla.py
import re
from app.extraction.geometry import box_center_y, box_left_x
from app.extraction.common import cluster_columns_by_x
from app.reference_data.hla_loci import HLA_LOCI

ROW_TOLERANCE_ABOVE = 10
ROW_TOLERANCE_BELOW = 45

# How far apart two header boxes can be (x-axis) and still count as the
# same column, e.g. a header wrapping "HLA" / "DRB1*" onto two lines.
# First-pass estimate — tune against real box coordinates once you have them.
COLUMN_X_TOLERANCE = 55

SKIP_ROW_LABELS = {"patient", "donor", "locus"}


def _squash(text: str) -> str:
    """'HLA-DRB3,4,5*' -> 'DRB345' so header text can be matched against
    canonical locus codes regardless of punctuation/spacing differences."""
    return re.sub(r"[^A-Z0-9,]", "", text.upper()).replace(",", "")


def _canonical_locus_lookup() -> dict[str, str]:
    return {_squash(locus): locus for locus in HLA_LOCI}


def _find_row_anchor(texts: list[str], boxes: list[list[int]], target: str, after_y: float = -1.0) -> int | None:
    for i, text in enumerate(texts):
        if text.strip().lower() == target and box_center_y(boxes[i]) > after_y:
            return i
    return None


def extract_hla(texts: list[str], boxes: list[list[int]]) -> dict:
    locus_idx = _find_row_anchor(texts, boxes, "locus")
    if locus_idx is None:
        return {"patient_hla": [], "donor_hla": [], "warning": "locus_header_not_found"}
    locus_y = box_center_y(boxes[locus_idx])

    patient_idx = _find_row_anchor(texts, boxes, "patient", after_y=locus_y)
    donor_idx = _find_row_anchor(texts, boxes, "donor", after_y=locus_y)
    if patient_idx is None or donor_idx is None:
        return {"patient_hla": [], "donor_hla": [], "warning": "patient_or_donor_row_not_found"}

    patient_y = box_center_y(boxes[patient_idx])
    donor_y = box_center_y(boxes[donor_idx])

    header_zone = [
        i for i, box in enumerate(boxes)
        if locus_y - ROW_TOLERANCE_ABOVE <= box_center_y(box) < patient_y - ROW_TOLERANCE_ABOVE
    ]
    columns = cluster_columns_by_x(header_zone, boxes, COLUMN_X_TOLERANCE)

    locus_lookup = _canonical_locus_lookup()
    column_loci: list[tuple[float, str]] = []
    for col in columns:
        col_sorted = sorted(col, key=lambda i: box_center_y(boxes[i]))  # top-to-bottom within the cell
        label_text = " ".join(texts[i] for i in col_sorted)
        canonical = locus_lookup.get(_squash(label_text))
        if canonical:
            x_center = sum(box_left_x(boxes[i]) for i in col_sorted) / len(col_sorted)
            column_loci.append((x_center, canonical))

    if not column_loci:
        return {"patient_hla": [], "donor_hla": [], "warning": "no_locus_columns_matched"}

    column_loci.sort(key=lambda pair: pair[0])

    def _extract_row(row_y: float, next_row_y: float | None) -> dict[str, list[tuple[float, str]]]:
        upper = (next_row_y - ROW_TOLERANCE_ABOVE) if next_row_y else (row_y + ROW_TOLERANCE_BELOW)
        by_column: dict[str, list[tuple[float, str]]] = {locus: [] for _, locus in column_loci}
        for i, box in enumerate(boxes):
            y = box_center_y(box)
            if not (row_y - ROW_TOLERANCE_ABOVE <= y < upper):
                continue
            if texts[i].strip().lower() in SKIP_ROW_LABELS:
                continue
            x = box_left_x(box)
            nearest_locus = min(column_loci, key=lambda pair: abs(pair[0] - x))[1]
            by_column[nearest_locus].append((x, texts[i].strip()))
        return by_column

    patient_cells = _extract_row(patient_y, donor_y)
    donor_cells = _extract_row(donor_y, None)

    def _cells_to_list(cells: dict[str, list[tuple[float, str]]]) -> list[dict]:
        result = []
        for _, locus in column_loci:
            ordered = sorted(cells.get(locus, []), key=lambda p: p[0])
            raw = " ".join(text for _, text in ordered)
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            result.append({
                "locus": locus,
                "allele_1": parts[0] if len(parts) > 0 else "",
                "allele_2": parts[1] if len(parts) > 1 else "",
            })
        return result

    return {
        "patient_hla": _cells_to_list(patient_cells),
        "donor_hla": _cells_to_list(donor_cells),
    }