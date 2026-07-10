# paddleocr-service/mfi_extraction.py
"""Extraction of the Bead Specificity Chart / MFI values from antibody
(Luminex) reports. Each page is a dense table: Bead | Sero | Allele Equiv
| MFI Baseline. Antigen name is read directly from the Sero column - no
external bead-to-antigen reference table is used.

No MFI threshold from clinical policy (e.g. the backend's DEFAULT_MFI_CUTOFF)
is applied here - only a much lower EXTRACTION_NOISE_FLOOR to drop the ~90
purely-zero baseline rows every page has. The doctor-configurable clinical
cutoff is applied at compatibility-check time on the backend, not baked
into extraction.

The header can span TWO physical OCR rows (e.g. "Bead"/"Sero"/"MFI" on one
line, "Allele Equiv"/"Baseline" wrapped onto the next) - confirmed by
inspecting raw detections on a real sample page. find_header_row() only
ever returns the single best-scoring row, so anything printed on a second
wrapped header line is invisible to it. _find_header_span() checks the row
immediately after the matched header row and folds it in if it looks like
a header continuation (contains column-name tokens, not table data), so
column centers are built from the FULL header regardless of how many
physical lines it was OCR'd into, and actual data extraction correctly
starts after every header line rather than treating a wrapped header line
as a phantom data row.

Column centers are matched by each header cell's OWN TEXT against known
tokens (BEAD / SERO / ALLELE / MFI / BASELINE), not by pairing header cells
to column names by position - positional pairing breaks silently whenever
a header cell goes missing or lands out of order, shifting every later
column onto the wrong x-position instead of failing loudly.
"""
from box_utils import group_into_rows
from table_extraction import extract_row_by_columns, find_header_row

HEADER_LABELS = ["BEAD", "SERO", "ALLELE", "MFI"]

HEADER_TOKEN_TO_COLUMN = [
    ("BEAD", "bead"),
    ("SERO", "sero"),
    ("ALLELE", "allele_equiv"),
    ("BASELINE", "mfi_baseline"),
    ("MFI", "mfi_baseline"),
]

# Tokens that mean "this row is still part of the header", used only to
# decide whether to fold a second physical line into the header span -
# separate from HEADER_TOKEN_TO_COLUMN so adding a new recognized token
# there doesn't have to also update matching logic here.
HEADER_CONTINUATION_TOKENS = ["ALLELE", "EQUIV", "BASELINE", "MFI", "BEAD", "SERO"]

EXTRACTION_NOISE_FLOOR = 0.0
LOW_CONFIDENCE_THRESHOLD = 0.75
MFI_ROW_Y_TOLERANCE = 8.0


def _looks_like_header_continuation(row: list[dict]) -> bool:
    row_text = " ".join(d["text"] for d in row).upper()
    return any(token in row_text for token in HEADER_CONTINUATION_TOKENS)


def _find_header_span(
    rows: list[list[dict]], header_labels: list[str]
) -> tuple[int, list[dict]] | None:
    """Locate the header and return (first_data_row_index, combined_header_cells).

    Starts from whatever single row find_header_row() scores best, then
    folds in any immediately-following row(s) that still look like header
    text (rather than a real bead/sero/MFI data row). This handles a
    header wrapping across two OCR'd lines, e.g. "Bead Sero MFI" on one
    line and "Allele Equiv Baseline" on the next.
    """
    header = find_header_row(rows, header_labels)
    if header is None:
        return None

    header_index, header_row = header
    combined_cells = list(header_row)
    next_index = header_index + 1

    while next_index < len(rows) and _looks_like_header_continuation(rows[next_index]):
        combined_cells.extend(rows[next_index])
        next_index += 1

    return next_index, combined_cells


def _build_column_centers(header_cells: list[dict]) -> list[tuple[float, str]]:
    """Match each header cell to a column name by its own text content.

    Returns a list of (center_x, column_name) pairs. If a column's header
    text was never detected anywhere in the header span, that column
    simply won't appear here - it won't be extracted for any data row,
    but it also won't drag any other column's position off.
    """
    column_centers: list[tuple[float, str]] = []
    seen_columns: set[str] = set()

    for cell in header_cells:
        upper = cell["text"].upper()
        for token, column_name in HEADER_TOKEN_TO_COLUMN:
            if token in upper and column_name not in seen_columns:
                column_centers.append((cell["center_x"], column_name))
                seen_columns.add(column_name)
                break

    return column_centers


def extract_mfi_values(detections: list[dict]) -> list[dict]:
    """Return a list of records, one per data row with a nonzero MFI:
    {
        "bead": str, "sero": str, "allele_equiv": str,
        "mfi_baseline": float, "mfi_baseline_raw": str,
        "confidence": float,       # min confidence across bead+sero+mfi cells
        "needs_review": bool,      # confidence too low, OR mfi unparseable
    }
    Rows that never resolve to a real (bead, sero) pair at all - footers,
    stray header repeats, page numbers - are skipped, since there's nothing
    to review there. Rows with a genuine bead/sero but an unparseable MFI
    are KEPT with needs_review=True rather than silently dropped, since a
    garbled number might still represent a real, significant antibody.
    """
    rows = group_into_rows(detections, y_tolerance=MFI_ROW_Y_TOLERANCE)

    header_span = _find_header_span(rows, HEADER_LABELS)
    if header_span is None:
        return []

    first_data_row_index, header_cells = header_span
    column_centers = _build_column_centers(header_cells)

    # If we couldn't match "bead", "sero", and "mfi_baseline" (the three
    # columns actually required downstream), there's nothing usable to
    # extract from this page - bail out rather than return garbage rows.
    matched_columns = {name for _, name in column_centers}
    if not {"bead", "sero", "mfi_baseline"}.issubset(matched_columns):
        return []

    records: list[dict] = []
    empty_field = {"text": "", "confidence": 0.0}

    for row in rows[first_data_row_index:]:
        row_text = " ".join(d["text"] for d in row).upper()

        if len(row) <= 1 and any(label in row_text for label in HEADER_LABELS):
            continue

        fields = extract_row_by_columns(row, column_centers)

        bead_field = fields.get("bead", empty_field)
        sero_field = fields.get("sero", empty_field)
        allele_field = fields.get("allele_equiv", empty_field)
        mfi_field = fields.get("mfi_baseline", empty_field)

        bead_text = bead_field.get("text", "")
        sero_text = sero_field.get("text", "")

        if not bead_text or not sero_text:
            continue

        mfi_raw = mfi_field.get("text", "")
        mfi_value = _parse_float(mfi_raw)

        if mfi_value is not None and mfi_value <= EXTRACTION_NOISE_FLOOR:
            continue

        confidences = [
            bead_field.get("confidence"),
            sero_field.get("confidence"),
            mfi_field.get("confidence"),
        ]
        confidences = [c for c in confidences if c is not None]
        confidence = min(confidences) if confidences else None

        missing_columns = any(
            k not in fields for k in ["bead", "sero", "mfi_baseline"]
        )

        needs_review = (
            mfi_value is None
            or confidence is None
            or confidence < LOW_CONFIDENCE_THRESHOLD
            or missing_columns
        )

        records.append(
            {
                "bead": bead_text,
                "sero": sero_text,
                "allele_equiv": allele_field.get("text", ""),
                "mfi_baseline": mfi_value,
                "mfi_baseline_raw": mfi_raw,
                "confidence": confidence,
                "needs_review": needs_review,
            }
        )

    return records


def to_antibody_profile_entries(records: list[dict]) -> list[dict]:
    """Convert extract_mfi_values() output into the shape the backend's
    AntibodyProfileEntry schema expects. Only includes records that have
    BOTH a real antigen name and a successfully-parsed MFI value - records
    still needing review for other reasons (e.g. low confidence) are
    included too, so the doctor sees them, but a record with no parseable
    MFI at all has nothing meaningful to submit and is excluded here (it's
    still visible in the raw "records" list for review).
    """
    entries: list[dict] = []

    for record in records:
        antigen = record["sero"].strip()
        mfi_value = record["mfi_baseline"]

        if not antigen or mfi_value is None:
            continue

        entries.append(
            {
                "antigen": antigen,
                "mfi": str(mfi_value),
                "needs_review": record["needs_review"],
            }
        )

    return entries


def _parse_float(raw_value: str) -> float | None:
    cleaned = raw_value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None