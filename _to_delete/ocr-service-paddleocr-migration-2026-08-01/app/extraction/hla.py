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
    canonical locus codes regardless of punctuation/spacing differences.
    Real report headers are printed as "HLA-A*", "HLA DQB1*", etc. — not
    just the bare locus code — so a leading "HLA" is stripped too, otherwise
    it never matches any entry in HLA_LOCI and the whole table silently
    comes back empty.

    PaddleOCR frequently misreads the digit "1" as a capital "I" in locus
    codes like "DRB1*"/"DQA1*" (rendering them "DRBI*"/"DQAI*"). No real
    entry in HLA_LOCI contains the letter "I", so normalizing I -> 1 here
    can only help matching, never cause a false match — confirmed 2026-07-30
    against a real report where "DRBI*" and "DQAI*" were silently dropped
    (never canonicalized to DRB1/DQA1) until this normalization was added."""
    squashed = re.sub(r"[^A-Z0-9,]", "", text.upper()).replace(",", "")
    squashed = squashed.replace("I", "1")
    if squashed.startswith("HLA"):
        squashed = squashed[3:]
    return squashed


def _split_multi_locus_label(label_text: str, locus_lookup: dict[str, str]) -> list[str] | None:
    """PaddleOCR sometimes detects two adjacent header cells as a single
    merged text box instead of two separate boxes — observed 2026-07-30 with
    "HLA DPA1* HLA DPB1*" coming back as one box, which meant DPA1 and DPB1
    could never canonicalize (the combined string matches neither code) and
    both silently vanished from the output with no warning.

    Each individual header on these reports starts with the literal "HLA"
    marker, so when a label's squash doesn't match any single canonical
    locus, split on that marker and try each piece independently. Returns
    the list of canonical loci in left-to-right order if every piece
    resolves, else None (leaving the caller to treat it as unmatched, same
    as before this existed)."""
    segments = [seg for seg in re.split(r"(?=HLA)", label_text.upper()) if seg.strip()]
    if len(segments) < 2:
        return None
    resolved = []
    for seg in segments:
        canonical = locus_lookup.get(_squash(seg))
        if not canonical:
            return None
        resolved.append(canonical)
    return resolved


def _canonical_locus_lookup() -> dict[str, str]:
    return {_squash(locus): locus for locus in HLA_LOCI}


def _find_row_anchor(texts: list[str], boxes: list[list[int]], target: str, after_y: float = -1.0) -> int | None:
    for i, text in enumerate(texts):
        if text.strip().lower() == target and box_center_y(boxes[i]) > after_y:
            return i
    return None


# Fallback when there's only one detected column to compare against — a
# generous default so a lone column doesn't accidentally exclude its own
# legitimate cell values.
DEFAULT_MAX_COLUMN_ASSIGNMENT_DISTANCE = 300.0


def _max_column_assignment_distance(column_loci: list[tuple[float, str]]) -> float:
    """Half the smallest gap between adjacent column centers. Used as a cap
    on how far a text box's x-position may be from the nearest column
    before it's excluded rather than force-assigned — otherwise stray text
    outside the table (most commonly a footnote below the last/donor row,
    which has no next-row boundary to stop at) always gets swept into
    whichever column happened to be least far away, however far that
    actually was."""
    if len(column_loci) < 2:
        return DEFAULT_MAX_COLUMN_ASSIGNMENT_DISTANCE
    xs = sorted(x for x, _ in column_loci)
    smallest_gap = min(b - a for a, b in zip(xs, xs[1:]))
    return smallest_gap / 2


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
            continue

        multi = _split_multi_locus_label(label_text, locus_lookup)
        if multi:
            # No sub-box boundary is available (PaddleOCR returned this as
            # one box), so split the merged box's x-range evenly across the
            # resolved loci in order. This only needs to be accurate enough
            # for _extract_row's nearest-column assignment below to prefer
            # the correct sub-column over the others — verified against a
            # real document's actual data-cell positions on 2026-07-30.
            left = min(box_left_x(boxes[i]) for i in col_sorted)
            right = max(boxes[i][2] for i in col_sorted)
            width = right - left
            n = len(multi)
            for idx, canonical in enumerate(multi):
                x_center = left + width * (idx + 0.5) / n
                column_loci.append((x_center, canonical))

    if not column_loci:
        return {"patient_hla": [], "donor_hla": [], "warning": "no_locus_columns_matched"}

    column_loci.sort(key=lambda pair: pair[0])

    max_column_distance = _max_column_assignment_distance(column_loci)

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
            nearest_x, nearest_locus = min(column_loci, key=lambda pair: abs(pair[0] - x))
            if abs(nearest_x - x) > max_column_distance:
                # Too far from every real column to plausibly be table data
                # — most often a footnote/disclaimer line sitting just below
                # the donor row (which has no next-row boundary to stop at).
                # Without this check it always got force-assigned to
                # whichever column was *least* far away, however far that
                # actually was — e.g. a footnote starting near the left
                # margin silently corrupting column A's donor allele.
                continue
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