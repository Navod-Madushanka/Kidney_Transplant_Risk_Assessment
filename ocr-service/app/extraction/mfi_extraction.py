# app/extraction/mfi_extraction.py
import re
from app.extraction.geometry import box_center_y, box_left_x
from app.extraction.common import cluster_columns_by_x, cluster_rows

HEADER_LABELS = {"bead", "sero", "allele", "equiv", "mfi", "baseline"}
COLUMN_X_TOLERANCE = 60
HEADER_ZONE_HEIGHT = 40  # px band below the topmost header label — tune against real coordinates


def _squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def extract_mfi_table(texts: list[str], boxes: list[list[int]]) -> dict:
    header_candidates = [i for i, t in enumerate(texts) if _squash(t) in HEADER_LABELS]
    if not header_candidates:
        return {"bead_specificity": [], "warning": "header_row_not_found"}

    header_top_y = min(box_center_y(boxes[i]) for i in header_candidates)
    header_zone = [i for i in header_candidates if box_center_y(boxes[i]) <= header_top_y + HEADER_ZONE_HEIGHT]
    columns = cluster_columns_by_x(header_zone, boxes, COLUMN_X_TOLERANCE)

    sero_x = mfi_x = None
    for col in columns:
        label = " ".join(_squash(texts[i]) for i in col)
        x_center = sum(box_left_x(boxes[i]) for i in col) / len(col)
        if "sero" in label:
            sero_x = x_center
        if "mfi" in label or "baseline" in label:
            mfi_x = x_center

    if sero_x is None or mfi_x is None:
        return {"bead_specificity": [], "warning": "sero_or_mfi_column_not_found"}

    header_bottom_y = max(box_center_y(boxes[i]) for i in header_zone)
    data_indices = [i for i, b in enumerate(boxes) if box_center_y(b) > header_bottom_y + 10]
    rows = cluster_rows(data_indices, boxes)

    entries = []
    for row in rows:
        sero_val = mfi_val = None
        for i in row:
            x = box_left_x(boxes[i])
            text = texts[i].strip()
            if not text:
                continue
            if abs(x - sero_x) <= abs(x - mfi_x):
                sero_val = text if sero_val is None else f"{sero_val} {text}"
            else:
                mfi_val = text if mfi_val is None else f"{mfi_val} {text}"
        if sero_val and mfi_val and re.search(r"\d", mfi_val):
            entries.append({"antigen": sero_val, "mfi": mfi_val})

    return {"bead_specificity": entries}