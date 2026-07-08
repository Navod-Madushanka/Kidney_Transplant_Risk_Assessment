# paddleocr-service/hla_typing.py
"""Extraction of the HLA Typing table from a Histocompatibility Type-match
Report (e.g. sample.jpg): the table with columns HLA-A*, HLA-B*, HLA-C*,
HLA DRB1*, HLA-DRB3,4,5*, HLA DQA1*, HLA DQB1*, HLA DPA1*, HLA DPB1*, and
Patient / Donor rows.

Output shape matches the backend's HLATypingEntry schema:
    {"locus": ..., "allele_1": ..., "allele_2": ...}
"""
from box_utils import group_into_rows
from table_extraction import (
    extract_row_by_columns,
    find_header_row,
    merge_short_continuation_rows,
)

HLA_HEADER_LABELS = [
    "HLA-A",
    "HLA-B",
    "HLA-C",
    "DRB1",
    "DRB3",
    "DQA1",
    "DQB1",
    "DPA1",
    "DPB1",
]

HLA_COLUMN_NAMES = [
    "row_label",
    "hla_a",
    "hla_b",
    "hla_c",
    "hla_drb1",
    "hla_drb345",
    "hla_dqa1",
    "hla_dqb1",
    "hla_dpa1",
    "hla_dpb1",
]

LOCUS_A = "A"
LOCUS_B = "B"
LOCUS_C = "C"
LOCUS_DRB1 = "DRB1"
LOCUS_DQA1 = "DQA1"
LOCUS_DQB1 = "DQB1"
LOCUS_DPA1 = "DPA1"
LOCUS_DPB1 = "DPB1"
DRB_COMBINED_LOCUS = "DRB3,4,5"

STANDARD_COLUMN_TO_LOCUS = {
    "hla_a": LOCUS_A,
    "hla_b": LOCUS_B,
    "hla_c": LOCUS_C,
    "hla_drb1": LOCUS_DRB1,
    "hla_dqa1": LOCUS_DQA1,
    "hla_dqb1": LOCUS_DQB1,
    "hla_dpa1": LOCUS_DPA1,
    "hla_dpb1": LOCUS_DPB1,
}

STOP_ROW_MARKERS = ["allele group-level resolution", "interpretation"]

LOW_CONFIDENCE_THRESHOLD = 0.75


def extract_hla_typing(detections: list[dict]) -> dict:
    """Return {"patient": [...], "donor": [...]}, where each entry is
    {"locus", "allele_1", "allele_2", "confidence", "needs_review"}.

    needs_review is True whenever the underlying OCR confidence for that
    cell fell below LOW_CONFIDENCE_THRESHOLD - the frontend should flag
    these for the doctor to check/correct before submitting.
    """
    rows = group_into_rows(detections)

    header = find_header_row(rows, HLA_HEADER_LABELS)
    if header is None:
        return {"patient": [], "donor": []}

    header_index, header_row = header
    column_names = _match_column_names(header_row)
    column_centers = list(zip((d["center_x"] for d in header_row), column_names))

    data_rows: list[list[dict]] = []
    for row in rows[header_index + 1 :]:
        row_text = " ".join(d["text"] for d in row).lower()
        if any(marker in row_text for marker in STOP_ROW_MARKERS):
            break
        data_rows.append(row)

    merged_rows = merge_short_continuation_rows(data_rows, len(column_centers))

    result: dict = {"patient": [], "donor": []}

    for row in merged_rows:
        fields = extract_row_by_columns(row, column_centers)
        row_label_field = fields.pop("row_label", {"text": "", "confidence": None})
        row_label = row_label_field["text"].strip().lower()

        entries = _row_fields_to_entries(fields)

        if row_label.startswith("patient"):
            result["patient"] = entries
        elif row_label.startswith("donor"):
            result["donor"] = entries

    return result


def _row_fields_to_entries(fields: dict[str, dict]) -> list[dict]:
    entries: list[dict] = []

    for column_name, field in fields.items():
        raw_value = field["text"]
        confidence = field["confidence"]

        if not raw_value:
            continue

        if column_name == "hla_drb345":
            entries.extend(_parse_multi_locus_cell(raw_value, confidence))
            continue

        locus = STANDARD_COLUMN_TO_LOCUS.get(column_name)
        if locus is None:
            continue

        alleles = [a.strip() for a in raw_value.split(",") if a.strip()]
        if not alleles:
            continue

        entries.append(
            {
                "locus": locus,
                "allele_1": alleles[0],
                "allele_2": alleles[1] if len(alleles) > 1 else alleles[0],
                "confidence": confidence,
                "needs_review": confidence is None
                or confidence < LOW_CONFIDENCE_THRESHOLD,
            }
        )

    return entries


def _parse_multi_locus_cell(raw_value: str, confidence: float | None) -> list[dict]:
    """Parse a combined cell like "DRB3*02, DRB4*01" into a SINGLE
    HLATypingEntry-shaped dict for the combined "DRB3,4,5" locus - the only
    value HLALocusEnum actually defines for this cell.
    """
    alleles: list[str] = []

    for token in raw_value.split(","):
        token = token.strip()
        if token:
            alleles.append(token)

    if not alleles:
        return []

    return [
        {
            "locus": DRB_COMBINED_LOCUS,
            "allele_1": alleles[0],
            "allele_2": alleles[1] if len(alleles) > 1 else alleles[0],
            "confidence": confidence,
            "needs_review": confidence is None
            or confidence < LOW_CONFIDENCE_THRESHOLD,
        }
    ]


def _match_column_names(header_row: list[dict]) -> list[str]:
    if len(header_row) == len(HLA_COLUMN_NAMES):
        return HLA_COLUMN_NAMES

    if len(header_row) < len(HLA_COLUMN_NAMES):
        return HLA_COLUMN_NAMES[: len(header_row)]

    extra = [f"extra_col_{i}" for i in range(len(HLA_COLUMN_NAMES), len(header_row))]
    return HLA_COLUMN_NAMES + extra