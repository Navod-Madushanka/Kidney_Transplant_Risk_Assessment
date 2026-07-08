# paddleocr-service/mfi_extraction.py
"""Extraction of the Bead Specificity Chart / MFI values used in antibody
(Luminex) reports, e.g. sample_mfi_page1.jpg and sample_mfi_page2.jpg.

Each page is a dense table: Bead | Sero | Allele Equiv | MFI Baseline
"""
from box_utils import group_into_rows
from table_extraction import extract_row_by_columns, find_header_row

HEADER_LABELS = ["BEAD", "SERO", "ALLELE", "MFI"]
COLUMN_NAMES = ["bead", "sero", "allele_equiv", "mfi_baseline"]


def extract_mfi_values(detections: list[dict]) -> list[dict]:
    """Return a list of {bead, sero, allele_equiv, mfi_baseline, mfi_baseline_raw}
    records, one per data row of the bead specificity chart. Returns an empty
    list if the table header couldn't be found on this page.
    """
    rows = group_into_rows(detections)

    header = find_header_row(rows, HEADER_LABELS)
    if header is None:
        return []

    header_index, header_row = header
    normalized_header = _normalize_header_row(header_row)
    column_centers = list(
        zip((cell["center_x"] for cell in normalized_header), COLUMN_NAMES)
    )

    records: list[dict] = []

    for row in rows[header_index + 1 :]:
        row_text = " ".join(d["text"] for d in row).upper()

        # Skip a stray second header line, e.g. a lone "Baseline" printed
        # under "MFI", rather than treating it as a data row.
        if len(row) <= 1 and any(label in row_text for label in HEADER_LABELS):
            continue

        fields = extract_row_by_columns(row, column_centers)

        if not fields.get("bead") or not fields.get("sero"):
            # Not a real table row (e.g. a footer line, date stamp, or
            # page number that happened to fall in this y-band).
            continue

        mfi_raw = fields.get("mfi_baseline", "")
        fields["mfi_baseline_raw"] = mfi_raw
        fields["mfi_baseline"] = _parse_float(mfi_raw)

        records.append(fields)

    return records


def to_antibody_profile_entries(records: list[dict]) -> list[dict]:
    """Convert extract_mfi_values() output into the exact shape the backend's
    AntibodyProfileEntry schema expects: [{"antigen": str, "mfi": str}, ...]

    `antigen` comes from the Sero column (e.g. "A23"), since that's the
    standard serologic antigen name used for antibody specificities and
    matches how the HLA typing report itself refers to antigens. `mfi` is
    kept as a string (rather than float) so Pydantic's Decimal field parses
    it without floating-point rounding surprises.

    No MFI threshold is applied here on purpose: the cutoff is
    doctor-configurable, so filtering by threshold should happen at
    compatibility-check time on the backend, not be baked into extraction.
    Every bead with a valid antigen and MFI is included; the doctor can
    still review/edit before this gets submitted.
    """
    entries: list[dict] = []

    for record in records:
        antigen = record.get("sero", "").strip()
        mfi_value = record.get("mfi_baseline")

        if not antigen or mfi_value is None:
            continue

        entries.append({"antigen": antigen, "mfi": str(mfi_value)})

    return entries


def _normalize_header_row(header_row: list[dict]) -> list[dict]:
    """Collapse a header row with more than 4 detected cells (e.g. "Allele"
    and "Equiv" captured as separate cells, or "MFI"/"Baseline" on two
    lines) down to exactly 4 column-anchor cells: Bead, Sero, Allele Equiv,
    MFI Baseline.
    """
    if len(header_row) <= 4:
        return header_row

    bead_cell = header_row[0]
    sero_cell = header_row[1]
    mfi_cell = header_row[-1]
    allele_cells = header_row[2:-1]

    allele_center_x = sum(c["center_x"] for c in allele_cells) / len(allele_cells)
    allele_text = " ".join(c["text"] for c in allele_cells)
    allele_cell = {**allele_cells[0], "center_x": allele_center_x, "text": allele_text}

    return [bead_cell, sero_cell, allele_cell, mfi_cell]


def _parse_float(raw_value: str) -> float | None:
    cleaned = raw_value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None