# paddleocr-service/app.py
import os
import shutil
import tempfile

from fastapi import FastAPI, UploadFile

from hla_typing import extract_hla_typing
from mfi_extraction import extract_mfi_values, to_antibody_profile_entries
from ocr_engine import get_ocr_engine
from patient_donor_details import extract_patient_donor_details

app = FastAPI(title="PaddleOCR Service")

# NOTE: This service does NOT call the backend. The doctor's JWT lives in
# the frontend, not here, so every endpoint below just returns extracted
# JSON for the frontend to show the doctor for review/correction. The
# frontend is responsible for submitting the (possibly edited) result to
# the backend (POST /patients, POST /donors, PUT .../hla-typings,
# PUT .../antibody-profiles) using the doctor's session.


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _run_ocr_on_upload(file: UploadFile) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = temp_file.name

    try:
        ocr = get_ocr_engine()
        result = ocr.ocr(temp_path, cls=True)

        detections = []
        for line in result:
            for detection in line:
                box = detection[0]
                text = detection[1][0]
                confidence = detection[1][1]
                detections.append({"text": text, "confidence": confidence, "box": box})

        return detections
    finally:
        os.remove(temp_path)


@app.post("/ocr")
async def run_ocr(file: UploadFile):
    """Raw OCR passthrough - all detected text/boxes, no parsing."""
    detections = _run_ocr_on_upload(file)
    return {"detections": detections}


@app.post("/ocr/patient-donor-details")
async def ocr_patient_donor_details(file: UploadFile):
    """Extracts patient/donor name, NIC, DOB, and blood type from the
    Histocompatibility report. Key names are close to PatientCreate /
    DonorCreate but haven't been forced to match exactly yet - double check
    against those schemas (full_name, date_of_birth, blood_type, nic_number)
    before wiring this into the frontend form.
    """
    detections = _run_ocr_on_upload(file)
    return extract_patient_donor_details(detections)


@app.post("/ocr/hla-typing")
async def ocr_hla_typing(file: UploadFile):
    """Extracts the HLA Typing table (Patient/Donor rows across all loci).

    Returns {"patient": [HLATypingEntry, ...], "donor": [HLATypingEntry, ...]}
    so the frontend can PUT the "patient" list to
    /patients/{patient_id}/hla-typings and the "donor" list to
    /donors/{donor_id}/hla-typings after doctor review.
    """
    detections = _run_ocr_on_upload(file)
    return extract_hla_typing(detections)


@app.post("/ocr/mfi-values")
async def ocr_mfi_values(file: UploadFile):
    """Extracts every bead row from one Bead Specificity Chart page. Call
    once per page (sample_mfi_page1.jpg, then sample_mfi_page2.jpg) and
    merge the "antibody_profile_entries" lists client-side before PUTting
    the combined list to /patients/{patient_id}/antibody-profiles.

    No MFI threshold is applied here - that's doctor-configurable and
    should be applied at compatibility-check time on the backend, not
    baked into extraction.
    """
    detections = _run_ocr_on_upload(file)
    records = extract_mfi_values(detections)

    return {
        "records": records,  # full detail (bead, sero, allele_equiv, mfi_baseline) for doctor review
        "antibody_profile_entries": to_antibody_profile_entries(records),  # ready for PUT .../antibody-profiles
    }