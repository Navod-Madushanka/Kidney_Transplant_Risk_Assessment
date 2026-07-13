from app.extraction.geometry import box_center_y, box_left_x

# Hardcoded column boundaries, calibrated from this report template's real
# coordinates. Locus order follows medical convention (standard HLA typing
# panel order), not something we expect to vary between reports from the
# same lab — but a genuinely different table layout would need recalibration.
LOCUS_COLUMNS = [
    ("HLA-A*", 176, 251),
    ("HLA-B*", 251, 350),
    ("HLA-C*", 350, 446),
    ("HLA-DRB1*", 446, 535),
    ("HLA-DRB3/4/5*", 535, 645),
    ("HLA-DQA1*", 645, 760),
    ("HLA-DQB1*", 760, 862),
    ("HLA-DPA1*", 862, 973),
    ("HLA-DPB1*", 973, 1250),
]

# How far below a row label's Y-center we still consider a box part of
# that row — generous enough to catch a wrapped second line underneath.
ROW_TOLERANCE_ABOVE = 10
ROW_TOLERANCE_BELOW = 45

SKIP_LABELS = {"Patient", "Donor", "Locus"}


def _locus_for_x(x_left: int) -> str | None:
    for name, start, end in LOCUS_COLUMNS:
        if start <= x_left < end:
            return name
    return None


def extract_hla(texts: list[str], boxes: list[list[int]]) -> dict:
    patient_row_y = None
    donor_row_y = None
    for i, text in enumerate(texts):
        if text.strip() == "Patient":
            patient_row_y = box_center_y(boxes[i])
        elif text.strip() == "Donor":
            donor_row_y = box_center_y(boxes[i])

    if patient_row_y is None or donor_row_y is None:
        return {"patient_hla": [], "donor_hla": []}

    patient_cells: dict[str, list[tuple[float, int, str]]] = {}
    donor_cells: dict[str, list[tuple[float, int, str]]] = {}

    for i, text in enumerate(texts):
        stripped = text.strip()
        if stripped in SKIP_LABELS:
            continue

        box = boxes[i]
        x_left = box_left_x(box)
        y_center = box_center_y(box)

        if x_left < LOCUS_COLUMNS[0][1]:
            continue  # to the left of the first data column — not a table value

        if patient_row_y - ROW_TOLERANCE_ABOVE <= y_center <= patient_row_y + ROW_TOLERANCE_BELOW:
            target = patient_cells
        elif donor_row_y - ROW_TOLERANCE_ABOVE <= y_center <= donor_row_y + ROW_TOLERANCE_BELOW:
            target = donor_cells
        else:
            continue  # part of the header row, or unrelated content

        locus = _locus_for_x(x_left)
        if locus is None:
            continue

        target.setdefault(locus, []).append((y_center, x_left, stripped))


    def _cells_to_list(cells: dict) -> list[dict]:
        result = []
        for locus_name, _, _ in LOCUS_COLUMNS:
            entries = cells.get(locus_name)
            if not entries:
                result.append({"locus": locus_name, "allele_1": "", "allele_2": ""})
                continue
            entries.sort(key=lambda e: (e[0], e[1]))  # top-to-bottom, then left-to-right
            combined = " ".join(e[2] for e in entries)
            parts = [p.strip() for p in combined.split(",")]
            result.append({
                "locus": locus_name,
                "allele_1": parts[0] if len(parts) > 0 else "",
                "allele_2": parts[1] if len(parts) > 1 else "",
            })
        return result

    return {
        "patient_hla": _cells_to_list(patient_cells),
        "donor_hla": _cells_to_list(donor_cells),
    }