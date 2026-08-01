# app/extraction/common.py
from app.extraction.geometry import box_center_y, box_left_x


def cluster_rows(indices: list[int], boxes: list[list[int]], y_tolerance: int = 15) -> list[list[int]]:
    """Groups box indices into visual rows by y-proximity, sorted
    top-to-bottom, each row's own indices sorted left-to-right."""
    ordered = sorted(indices, key=lambda i: box_center_y(boxes[i]))
    rows: list[list[int]] = []
    for idx in ordered:
        y = box_center_y(boxes[idx])
        placed = False
        for row in rows:
            row_y = box_center_y(boxes[row[0]])
            if abs(row_y - y) <= y_tolerance:
                row.append(idx)
                placed = True
                break
        if not placed:
            rows.append([idx])
    for row in rows:
        row.sort(key=lambda i: box_left_x(boxes[i]))
    return rows


def cluster_columns_by_x(indices: list[int], boxes: list[list[int]], x_tolerance: int) -> list[list[int]]:
    """Groups box indices into columns by x-proximity — used to treat a
    header that wraps onto two lines (e.g. 'HLA' over 'DRB1*') as one
    column rather than two."""
    ordered = sorted(indices, key=lambda i: box_left_x(boxes[i]))
    columns: list[list[int]] = []
    for idx in ordered:
        x = box_left_x(boxes[idx])
        placed = False
        for col in columns:
            col_x = box_left_x(boxes[col[0]])
            if abs(col_x - x) <= x_tolerance:
                col.append(idx)
                placed = True
                break
        if not placed:
            columns.append([idx])
    return columns


def row_text(row: list[int], texts: list[str]) -> str:
    return " ".join(texts[i].strip() for i in row if texts[i].strip())


def value_after_label_same_row(label_index: int, texts: list[str], boxes: list[list[int]]) -> str | None:
    label_box = boxes[label_index]
    candidates = []
    for j, other_box in enumerate(boxes):
        if j == label_index:
            continue
        if abs(box_center_y(other_box) - box_center_y(label_box)) <= 15 and box_left_x(other_box) > box_left_x(label_box):
            candidates.append((box_left_x(other_box), texts[j].strip()))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return " ".join(text for _, text in candidates if text)


def value_in_row_below(label_index: int, rows: list[list[int]], texts: list[str], boxes: list[list[int]]) -> str | None:
    """Fallback for labels whose value sits on the row *underneath* rather
    than to the right (e.g. 'Interpretation:' with a sentence below it)."""
    label_y = box_center_y(boxes[label_index])
    later_rows = [r for r in rows if box_center_y(boxes[r[0]]) > label_y]
    if not later_rows:
        return None
    later_rows.sort(key=lambda r: box_center_y(boxes[r[0]]))
    return row_text(later_rows[0], texts)