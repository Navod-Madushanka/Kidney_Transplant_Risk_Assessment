# app/extraction/crossmatch_extraction.py
import re
from app.extraction.demographics import extract_demographics
from app.extraction.common import cluster_rows, value_after_label_same_row, value_in_row_below

FIELD_LABEL_VARIANTS: dict[str, list[str]] = {
    "t_cell_result": ["T Cell cross match", "T-Cell Crossmatch"],
    "b_cell_result": ["B Cell cross match", "B-Cell Crossmatch"],
    "interpretation": ["Interpretation"],
    "remarks": ["Remarks"],
    "test_date": ["Date"],
}

# Values written on the line below the label rather than beside it.
NEXT_ROW_FIELDS = {"interpretation"}


def _build_combined_pattern(variants: list[str]) -> re.Pattern:
    escaped = [re.escape(v) for v in variants]
    return re.compile(rf"(?:{'|'.join(escaped)})\s*:\s*(.+)", re.IGNORECASE)


COMBINED_PATTERNS = {field: _build_combined_pattern(v) for field, v in FIELD_LABEL_VARIANTS.items()}


def extract_crossmatch(texts: list[str], boxes: list[list[int]]) -> dict:
    demographics = extract_demographics(texts, boxes)

    result = {field: "" for field in FIELD_LABEL_VARIANTS}
    rows = cluster_rows(list(range(len(boxes))), boxes)
    matched_indices: set[int] = set()

    for i, text in enumerate(texts):
        for field, pattern in COMBINED_PATTERNS.items():
            if pattern.search(text):
                result[field] = pattern.search(text).group(1).strip()
                matched_indices.add(i)

    for i, text in enumerate(texts):
        if i in matched_indices:
            continue
        stripped = text.strip().lower()
        for field, variants in FIELD_LABEL_VARIANTS.items():
            if result[field]:
                continue
            if any(stripped == v.lower() or stripped.startswith(v.lower()) for v in variants):
                value = (
                    value_in_row_below(i, rows, texts, boxes)
                    if field in NEXT_ROW_FIELDS
                    else value_after_label_same_row(i, texts, boxes)
                )
                if value:
                    result[field] = value.lstrip(":").strip()
                break

    return {"crossmatch": result, **demographics}