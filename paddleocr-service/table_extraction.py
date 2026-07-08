# paddleocr-service/table_extraction.py
"""Generic column-based table extraction for OCR detections.

Used for tabular reports (e.g. the HLA typing table and the MFI / bead
specificity chart) where a header row defines named columns and every row
beneath it should be sliced into those columns by horizontal position,
rather than by ":" label/value pairs (which box_utils/patient_donor_details
already handle).
"""


def find_header_row(
    rows: list[list[dict]], header_labels: list[str]
) -> tuple[int, list[dict]] | None:
    """Find the row that best matches the given header labels.

    Scores every row by how many of `header_labels` appear (case-insensitive
    substring match) among its detections' text, and returns the best-scoring
    row as (row_index, row). Returns None if no row scores at least half of
    the expected labels (minimum 2), which usually means the table wasn't
    found on this page.
    """
    best_index = None
    best_row = None
    best_score = 0

    for index, row in enumerate(rows):
        row_text = " | ".join(d["text"].upper() for d in row)
        score = sum(1 for label in header_labels if label.upper() in row_text)

        if score > best_score:
            best_score = score
            best_index = index
            best_row = row

    if best_index is None or best_score < max(2, len(header_labels) // 2):
        return None

    return (best_index, best_row)


def extract_row_by_columns(
    row: list[dict],
    column_centers: list[tuple[float, str]],
    max_distance: float = 150.0,
) -> dict[str, dict]:
    """Assign each detection in a data row to its nearest header column.

    `column_centers` is a list of (x_center, column_name) pairs, typically
    taken from a header row. Multiple detections landing in the same column
    (e.g. a cell value that OCR split across two lines) are joined with a
    space, left-to-right. Detections farther than `max_distance` from every
    column center are ignored, to avoid pulling in stray text (footers,
    page numbers, signatures) that isn't actually part of the table.

    Returns {column_name: {"text": str, "confidence": float}} - confidence
    is the MINIMUM confidence across every detection joined into that cell,
    since a combined value is only as trustworthy as its weakest piece.
    Callers that only need the text can do result[name]["text"].
    """
    buckets: dict[str, list[dict]] = {name: [] for _, name in column_centers}

    for detection in row:
        nearest_center, nearest_name = min(
            column_centers, key=lambda c: abs(c[0] - detection["center_x"])
        )
        if abs(nearest_center - detection["center_x"]) <= max_distance:
            buckets[nearest_name].append(detection)

    result: dict[str, dict] = {}
    for name, cells in buckets.items():
        cells.sort(key=lambda d: d["center_x"])
        text = " ".join(cell["text"].strip() for cell in cells).strip()

        if cells:
            confidence = min(cell["confidence"] for cell in cells)
        else:
            confidence = None

        result[name] = {"text": text, "confidence": confidence}

    return result


def merge_short_continuation_rows(
    rows: list[list[dict]], expected_column_count: int
) -> list[list[dict]]:
    """Fold short continuation rows into the previous full data row.

    Some table cells wrap onto a second line (e.g. "DRB3*02," on one line and
    "DRB4*01" directly beneath it inside the same cell). group_into_rows will
    see that as a separate row since it groups purely by y-position. Any row
    with far fewer detections than a full row is treated as a wrapped
    continuation of the row above it and merged in, rather than treated as
    a table row of its own.
    """
    merged: list[list[dict]] = []

    for row in rows:
        is_continuation = merged and len(row) < expected_column_count / 2
        if is_continuation:
            merged[-1] = merged[-1] + row
        else:
            merged.append(row)

    return merged