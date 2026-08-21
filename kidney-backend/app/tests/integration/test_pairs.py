# app/tests/integration/test_pairs.py
"""
Coverage for POST /pairs and the pair-scoped report-file routes (see
app/services/pair_service.py, app/api/pairs.py) — registering a patient and
donor together, plus the pair record that owns the two joint lab documents
(HLA typing report, crossmatch report). See
implementation-prompt-part-f.md F11 for the scenarios this is meant to
cover.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.audit_log import AuditLog
from app.models.donor import Donor
from app.models.donor_hla_typing import DonorHLATyping
from app.models.donor_patient_pair import DonorPatientPair
from app.models.patient import Patient
from app.models.patient_hla_typing import PatientHLATyping
from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    make_donor_payload,
    make_patient_payload,
)

PDF_BYTES = b"%PDF-1.4 fake report bytes for testing"


def _pair_payload(**overrides):
    payload = {
        "patient": make_patient_payload(),
        "donor": make_donor_payload(),
        "patient_hla": COMPATIBLE_PATIENT_HLA,
        "donor_hla": COMPATIBLE_DONOR_HLA,
        "crossmatch": {
            "t_cell_result": "Negative",
            "b_cell_result": "Negative",
            "interpretation": "No evidence of donor-specific antibodies.",
            "remarks": None,
            "test_date": "2026-08-01",
        },
    }
    payload.update(overrides)
    return payload


async def _upload(client: AsyncClient, pair_id: str, **overrides):
    data = {"category": overrides.get("category", "hla_typing_report")}
    filename = overrides.get("filename", "report.pdf")
    content = overrides.get("content", PDF_BYTES)
    content_type = overrides.get("content_type", "application/pdf")
    return await client.post(
        f"/pairs/{pair_id}/report-files",
        data=data,
        files={"file": (filename, content, content_type)},
    )


async def test_register_pair_happy_path(auth_client: AsyncClient, db_session):
    response = await auth_client.post("/pairs", json=_pair_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["patient"]["full_name"] == "Alice Patient"
    assert body["donor"]["full_name"] == "Bob Donor"
    patient_id = body["patient_id"]
    donor_id = body["donor_id"]

    # Exactly one row of each -- and donor.intended_recipient_id set.
    patient_rows = (
        await db_session.execute(select(Patient).where(Patient.id == patient_id))
    ).scalars().all()
    donor_rows = (
        await db_session.execute(select(Donor).where(Donor.id == donor_id))
    ).scalars().all()
    pair_rows = (
        await db_session.execute(
            select(DonorPatientPair).where(DonorPatientPair.patient_id == patient_id)
        )
    ).scalars().all()
    assert len(patient_rows) == 1
    assert len(donor_rows) == 1
    assert len(pair_rows) == 1
    assert str(donor_rows[0].intended_recipient_id) == patient_id

    # Both HLA typing tables populated (9 loci each).
    patient_hla = (
        await db_session.execute(
            select(PatientHLATyping).where(PatientHLATyping.patient_id == patient_id)
        )
    ).scalars().all()
    donor_hla = (
        await db_session.execute(
            select(DonorHLATyping).where(DonorHLATyping.donor_id == donor_id)
        )
    ).scalars().all()
    assert len(patient_hla) == 9
    assert len(donor_hla) == 9

    # Exactly one audit entry -- regression test for the doctor_id=None
    # requirement on the internal HLA-replace calls (see app/api/pairs.py).
    audit_rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.action == "registered_pair"))
    ).scalars().all()
    assert len(audit_rows) == 1
    assert audit_rows[0].patient_id is not None and str(audit_rows[0].patient_id) == patient_id
    assert audit_rows[0].donor_id is not None and str(audit_rows[0].donor_id) == donor_id


async def test_register_pair_donor_nic_conflict_rolls_back_the_patient_too(
    auth_client: AsyncClient, db_session
):
    existing_donor = await auth_client.post(
        "/donors", json=make_donor_payload(nic_number="900000001V")
    )
    assert existing_donor.status_code == 201

    response = await auth_client.post(
        "/pairs",
        json=_pair_payload(
            patient=make_patient_payload(nic_number="800000001V"),
            donor=make_donor_payload(nic_number="900000001V"),
        ),
    )

    assert response.status_code == 409

    patients = (
        await db_session.execute(select(Patient).where(Patient.nic_number == "800000001V"))
    ).scalars().all()
    assert patients == []


async def test_register_pair_patient_nic_conflict_rolls_back_everything(
    auth_client: AsyncClient, db_session
):
    existing_patient = await auth_client.post(
        "/patients", json=make_patient_payload(nic_number="800000002V")
    )
    assert existing_patient.status_code == 201

    response = await auth_client.post(
        "/pairs",
        json=_pair_payload(
            patient=make_patient_payload(nic_number="800000002V"),
            donor=make_donor_payload(nic_number="900000002V"),
        ),
    )

    assert response.status_code == 409

    donors = (
        await db_session.execute(select(Donor).where(Donor.nic_number == "900000002V"))
    ).scalars().all()
    assert donors == []


async def test_upload_bead_category_to_a_pair_is_rejected(auth_client: AsyncClient):
    register = await auth_client.post("/pairs", json=_pair_payload())
    pair_id = register.json()["id"]

    response = await _upload(auth_client, pair_id, category="bead_specificity_chart_page_1")

    assert response.status_code == 422


async def test_duplicate_active_pair_conflicts_then_succeeds_after_soft_delete(
    auth_client: AsyncClient, db_session
):
    # POST /pairs always mints a brand-new patient+donor, so there's no
    # HTTP-level way to hit the (patient_id, donor_id) partial-unique index
    # directly (re-using a NIC 409s on the patient/donor create first) --
    # this exercises the DB constraint pair_service.create_pair relies on
    # directly, same as the model layer it's protecting.
    register = await auth_client.post("/pairs", json=_pair_payload())
    assert register.status_code == 201
    body = register.json()
    patient_id = uuid.UUID(body["patient_id"])
    donor_id = uuid.UUID(body["donor_id"])
    doctor_id = uuid.UUID(body["doctor_id"])

    from app.services.pair_service import create_pair

    with pytest.raises(IntegrityError):
        await create_pair(db_session, doctor_id, patient_id, donor_id, None, True)
    await db_session.rollback()

    # Soft-delete the original pair frees the combination for re-registration.
    await db_session.execute(
        update(DonorPatientPair)
        .where(DonorPatientPair.patient_id == patient_id, DonorPatientPair.donor_id == donor_id)
        .values(is_deleted=True)
    )
    await db_session.commit()

    recreated = await create_pair(db_session, doctor_id, patient_id, donor_id, None, True)
    assert recreated is not None


async def test_cross_doctor_pair_endpoints_404(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    register = await auth_client.post("/pairs", json=_pair_payload())
    pair_id = register.json()["id"]

    upload = await _upload(second_auth_client, pair_id)
    get_one = await second_auth_client.get(f"/pairs/{pair_id}")
    list_files = await second_auth_client.get(f"/pairs/{pair_id}/report-files")

    assert upload.status_code == 404
    assert get_one.status_code == 404
    assert list_files.status_code == 404


async def test_pair_read_detects_intended_recipient_drift(auth_client: AsyncClient, db_session):
    register = await auth_client.post("/pairs", json=_pair_payload())
    body = register.json()
    pair_id = body["id"]
    donor_id = body["donor_id"]

    # Simulate the donor's intended_recipient_id drifting away from this
    # pair via a direct write (e.g. PUT /donors/{id} repointing it), which
    # app/api/pairs.py's own contract deliberately leaves possible -- see
    # DonorPatientPair's docstring and F2.2.
    await db_session.execute(
        update(Donor).where(Donor.id == donor_id).values(intended_recipient_id=None)
    )
    await db_session.commit()

    response = await auth_client.get(f"/pairs/{pair_id}")

    assert response.status_code == 409
