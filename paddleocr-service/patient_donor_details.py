# paddleocr-service/patient_donor_details.py
from datetime import date, datetime

from box_utils import group_into_rows

PAGE_MIDPOINT_X = 500.0

BLOOD_GROUP_MAP = {
    "A POSITIVE": "A",
    "A NEGATIVE": "A",
    "B POSITIVE": "B",
    "B NEGATIVE": "B",
    "AB POSITIVE": "AB",
    "AB NEGATIVE": "AB",
    "O POSITIVE": "O",
    "O NEGATIVE": "O",
}

DATE_FORMATS = ["%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"]


def split_label_value(text: str) -> tuple[str, str] | None:
    if ":" not in text:
        return None

    label, _, value = text.partition(":")
    return (label.strip(), value.strip())


def split_row_by_side(row: list[dict]) -> tuple[list[dict], list[dict]]:
    patient_side = [d for d in row if d["center_x"] < PAGE_MIDPOINT_X]
    donor_side = [d for d in row if d["center_x"] >= PAGE_MIDPOINT_X]

    return (patient_side, donor_side)


def extract_label_value_from_side(side: list[dict]) -> tuple[str, str] | None:
    if len(side) < 2:
        return None

    label_detection = side[0]
    value_detection = side[1]

    return (label_detection["text"].strip(), value_detection["text"].strip())


def normalize_blood_type(raw_value: str) -> str | None:
    cleaned = raw_value.upper().replace(",", " ").strip()

    if cleaned in BLOOD_GROUP_MAP:
        return BLOOD_GROUP_MAP[cleaned]

    for key, value in BLOOD_GROUP_MAP.items():
        no_space_key = key.replace(" ", "")
        no_space_cleaned = cleaned.replace(" ", "")
        if no_space_cleaned == no_space_key:
            return value

    return None


def parse_date(raw_value: str) -> date | None:
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(raw_value, date_format).date()
        except ValueError:
            continue

    return None


def extract_patient_donor_details(detections: list[dict]) -> dict:
    patient_data: dict = {}
    donor_data: dict = {}

    for detection in detections:
        parsed = split_label_value(detection["text"])
        if parsed is None:
            continue

        label, value = parsed
        if label == "Name of the Patient":
            patient_data["full_name"] = value
        elif label == "Name of the Donor":
            donor_data["full_name"] = value

    rows = group_into_rows(detections)

    for row in rows:
        patient_side, donor_side = split_row_by_side(row)

        patient_pair = extract_label_value_from_side(patient_side)
        if patient_pair is not None:
            label, value = patient_pair
            _apply_field(patient_data, label, value)

        donor_pair = extract_label_value_from_side(donor_side)
        if donor_pair is not None:
            label, value = donor_pair
            _apply_field(donor_data, label, value)

    return {"patient": patient_data, "donor": donor_data}


def _apply_field(target: dict, label: str, value: str) -> None:
    if label == "NIC":
        target["nic_number"] = value
    elif label == "DOB":
        target["date_of_birth_raw"] = value
        parsed_date = parse_date(value)
        target["date_of_birth"] = parsed_date.isoformat() if parsed_date else None
    elif label == "Blood Group":
        normalized = normalize_blood_type(value)
        target["blood_type"] = normalized
        target["blood_type_raw"] = value