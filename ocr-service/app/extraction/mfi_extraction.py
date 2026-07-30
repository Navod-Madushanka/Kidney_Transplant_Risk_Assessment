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

    # Classify every header column we can see (bead / sero / allele+equiv /
    # mfi+baseline), not just sero and mfi. The real chart has four columns;
    # comparing a data box against only two reference points meant "Bead"
    # numbers and "Allele Equiv" text always got glued onto whichever of
    # sero/mfi happened to be nearer — usually sero, polluting the antigen
    # field with stray bead numbers and allele codes.
    column_roles: list[tuple[float, str]] = []
    for col in columns:
        label = " ".join(_squash(texts[i]) for i in col)
        x_center = sum(box_left_x(boxes[i]) for i in col) / len(col)
        if "sero" in label:
            column_roles.append((x_center, "sero"))
        elif "mfi" in label or "baseline" in label:
            column_roles.append((x_center, "mfi"))
        elif "bead" in label:
            column_roles.append((x_center, "bead"))
        elif "allele" in label or "equiv" in label:
            column_roles.append((x_center, "allele_equiv"))

    has_sero = any(role == "sero" for _, role in column_roles)
    has_mfi = any(role == "mfi" for _, role in column_roles)
    if not has_sero or not has_mfi:
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
            nearest_role = min(column_roles, key=lambda pair: abs(pair[0] - x))[1]
            if nearest_role == "sero":
                sero_val = text if sero_val is None else f"{sero_val} {text}"
            elif nearest_role == "mfi":
                mfi_val = text if mfi_val is None else f"{mfi_val} {text}"
            # "bead" and "allele_equiv" columns are deliberately dropped —
            # we only need the antigen (sero) and MFI value per row.
        if sero_val and mfi_val and re.search(r"\d", mfi_val):
            entries.append({"antigen": sero_val, "mfi": mfi_val})

    return {"bead_specificity": entries}