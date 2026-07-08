# paddleocr-service/hla_typing.py
"""Extraction of the HLA Typing table from a Histocompatibility Type-match
Report. Column headers are identified by scanning every detection's text
directly for known locus tokens (not by picking a single "header row"),
since real headers often wrap across two physical lines. Patient/Donor
rows are identified by literal text search too, not by column position,
since the label can sit very close to the first data column.
"""

HEADER_TOKEN_TO_COLUMN = [
    ("HLA-A", "hla_a"),
    ("HLA-B", "hla_b"),
    ("HLA-C", "hla_c"),
    ("DRB1", "hla_drb1"),
    ("DRB3", "hla_drb345"),
    ("DQA1", "hla_dqa1"),
    ("DQB1", "hla_dqb1"),
    ("DPA1", "hla_dpa1"),
    ("DPB1", "hla_dpb1"),
]

STANDARD_COLUMN_TO_LOCUS = {
    "hla_a": "A",
    "hla_b": "B",
    "hla_c": "C",
    "hla_drb1": "DRB1",
    "hla_dqa1": "DQA1",
    "hla_dqb1": "DQB1",
    "hla_dpa1": "DPA1",
    "hla_dpb1": "DPB1",
}

DRB_COMBINED_LOCUS = "DRB3,4,5"
STOP_ROW_MARKERS = ["allele group-level resolution", "interpretation"]
LOW_CONFIDENCE_THRESHOLD = 0.75
MAX_COLUMN_DISTANCE = 60.0

from box_utils import group_into_rows


def _normalize_for_header_match(text: str) -> str:
    # Corrects the common OCR confusion of the digit "1" reading as the
    # letter "I" (e.g. "DQB1*" misread as "DQBI*"), specifically for
    # matching header tokens - never used on actual allele values.
    return text.upper().replace("I", "1")


def _is_patient_or_donor_label(text: str) -> str | None:
    upper = text.strip().upper()
    if upper.startswith("PATIENT"):
        return "patient"
    if upper.startswith("DONOR"):
        return "donor"
    return None


def _build_column_centers(header_rows: list[list[dict]]) -> list[tuple[float, str]]:
    column_centers: list[tuple[float, str]] = []
    seen_columns: set[str] = set()

    for row in header_rows:
        for detection in row:
            normalized = _normalize_for_header_match(detection["text"])
            for token, column_name in HEADER_TOKEN_TO_COLUMN:
                if token in normalized and column_name not in seen_columns:
                    column_centers.append((detection["center_x"], column_name))
                    seen_columns.add(column_name)

    return column_centers


def extract_hla_typing(detections: list[dict]) -> dict:
    """Return {"patient": [...], "donor": [...]}, where each entry is
    {"locus", "allele_1", "allele_2", "confidence", "needs_review"}.
    """
    rows = group_into_rows(detections)

    label_positions: list[tuple[int, str, dict]] = []
    for row_index, row in enumerate(rows):
        for detection in row:
            side = _is_patient_or_donor_label(detection["text"])
            if side is not None:
                label_positions.append((row_index, side, detection))
                break

    if not label_positions:
        return {"patient": [], "donor": []}

    header_rows = rows[: label_positions[0][0]]
    column_centers = _build_column_centers(header_rows)
    if not column_centers:
        return {"patient": [], "donor": []}

    result: dict = {"patient": [], "donor": []}

    for i, (row_index, side, label_detection) in enumerate(label_positions):
        end_index = (
            label_positions[i + 1][0] if i + 1 < len(label_positions) else len(rows)
        )

        block_detections: list[dict] = []
        for row in rows[row_index:end_index]:
            row_text = " ".join(d["text"] for d in row).lower()
            if any(marker in row_text for marker in STOP_ROW_MARKERS):
                break
            block_detections.extend(d for d in row if d is not label_detection)

        result[side] = _extract_entries(block_detections, column_centers)

    return result


def _extract_entries(
    detections: list[dict], column_centers: list[tuple[float, str]]
) -> list[dict]:
    buckets: dict[str, list[dict]] = {name: [] for _, name in column_centers}

    for detection in detections:
        nearest_center, nearest_name = min(
            column_centers, key=lambda c: abs(c[0] - detection["center_x"])
        )
        if abs(nearest_center - detection["center_x"]) <= MAX_COLUMN_DISTANCE:
            buckets[nearest_name].append(detection)

    entries: list[dict] = []
    for column_name, cells in buckets.items():
        if not cells:
            continue

        cells.sort(key=lambda c: c["center_x"])
        raw_value = " ".join(c["text"].strip() for c in cells).strip()
        confidence = min(c["confidence"] for c in cells)

        if column_name == "hla_drb345":
            entries.extend(_parse_multi_locus_cell(raw_value, confidence))
            continue

        locus = STANDARD_COLUMN_TO_LOCUS.get(column_name)
        if locus is None:
            continue

        alleles = [a.strip() for a in raw_value.replace(".", ",").split(",") if a.strip()]
        if not alleles:
            continue

        entries.append(
            {
                "locus": locus,
                "allele_1": alleles[0],
                "allele_2": alleles[1] if len(alleles) > 1 else alleles[0],
                "confidence": confidence,
                "needs_review": confidence < LOW_CONFIDENCE_THRESHOLD,
            }
        )

    return entries


def _parse_multi_locus_cell(raw_value: str, confidence: float) -> list[dict]:
    alleles = [token.strip() for token in raw_value.split(",") if token.strip()]
    if not alleles:
        return []

    return [
        {
            "locus": DRB_COMBINED_LOCUS,
            "allele_1": alleles[0],
            "allele_2": alleles[1] if len(alleles) > 1 else alleles[0],
            "confidence": confidence,
            "needs_review": confidence < LOW_CONFIDENCE_THRESHOLD,
        }
    ]