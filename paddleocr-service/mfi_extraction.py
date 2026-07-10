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

Column centers are found by matching each header cell's OWN TEXT against
known tokens (BEAD / SERO / ALLELE / MFI / BASELINE), not by pairing
header cells to COLUMN_NAMES by position. Positional pairing breaks silently
whenever a column's header text gets OCR'd into a separate row/cell than
expected (e.g. "Allele Equiv" splitting off or landing outside the y-band
of the rest of the header row) - it just shifts every later column name
onto the wrong x-position instead of failing loudly. Text-based matching
means a missing header cell just means that one column doesn't get
extracted, instead of corrupting every column after it.
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

EXTRACTION_NOISE_FLOOR = 0.0
LOW_CONFIDENCE_THRESHOLD = 0.75
MFI_ROW_Y_TOLERANCE = 8.0


def _build_column_centers(header_row: list[dict]) -> list[tuple[float, str]]:
    """Match each header cell to a column name by its own text content.

    Returns a list of (center_x, column_name) pairs. If a column's header
    text was never detected (e.g. "Allele Equiv" got OCR'd into a
    neighboring row and merge_wrapped_lines/group_into_rows missed it),
    that column simply won't appear here - it will not be extracted for
    any data row, but it also won't drag every other column's position off.
    """
    column_centers: list[tuple[float, str]] = []
    seen_columns: set[str] = set()

    for cell in header_row:
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

    header = find_header_row(rows, HEADER_LABELS)
    if header is None:
        return []

    header_index, header_row = header
    column_centers = _build_column_centers(header_row)

    # If we couldn't even match "bead", "sero", and "mfi_baseline" (the
    # three columns actually required downstream), there's nothing usable
    # to extract from this page - bail out rather than return garbage rows.
    matched_columns = {name for _, name in column_centers}
    if not {"bead", "sero", "mfi_baseline"}.issubset(matched_columns):
        return []

    records: list[dict] = []
    empty_field = {"text": "", "confidence": 0.0}

    for row in rows[header_index + 1 :]:
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