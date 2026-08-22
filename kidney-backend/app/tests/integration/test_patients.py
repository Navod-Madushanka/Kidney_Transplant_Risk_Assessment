# app/tests/integration/test_patients.py
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.tests.conftest import create_patient, make_patient_payload, register_test_doctor


async def test_create_patient(auth_client: AsyncClient):
    response = await auth_client.post("/patients", json=make_patient_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Alice Patient"
    assert body["blood_type"] == "AB"
    assert body["rh_factor"] == "+"
    assert "id" in body


async def test_create_patient_requires_auth(client: AsyncClient):
    response = await client.post("/patients", json=make_patient_payload())

    assert response.status_code in (401, 403)


async def test_create_patient_rejects_missing_required_fields(auth_client: AsyncClient):
    response = await auth_client.post("/patients", json={"full_name": "Incomplete"})

    assert response.status_code == 422


async def test_duplicate_nic_for_same_doctor_returns_clean_conflict(auth_client: AsyncClient):
    # Regression test for a real bug (found 2026-08-03): this used to crash
    # with an unhandled 500 (raw asyncpg.UniqueViolationError) instead of a
    # clean error.
    await create_patient(auth_client, nic_number="200000000001")

    response = await auth_client.post(
        "/patients", json=make_patient_payload(full_name="Someone Else", nic_number="200000000001")
    )

    assert response.status_code == 409


async def test_two_different_doctors_can_use_the_same_nic(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # Regression test for a real bug (found 2026-08-03): patients are
    # strictly doctor-isolated everywhere else in this codebase (unlike
    # donors), but nic_number used to be a GLOBAL unique constraint -- so
    # two different doctors independently treating two different real
    # people who happen to share an NIC (or re-running the same real
    # patient's paperwork under a second doctor account) would crash. NIC
    # uniqueness is now scoped per-doctor to match the isolation model.
    first = await create_patient(auth_client, nic_number="200000000001")
    second = await create_patient(second_auth_client, nic_number="200000000001")

    assert first["id"] != second["id"]
    assert first["nic_number"] == second["nic_number"] == "200000000001"


async def test_list_patients_returns_only_this_doctors_patients(
    auth_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    await create_patient(auth_client, full_name="Doctor A's Patient")

    # A second doctor, provisioned independently, should see an empty list —
    # patients are scoped per doctor, not shared across the hospital.
    other_doctor = await register_test_doctor(
        db_session,
        hospital_name="Other Hospital",
        email="other-doctor@example.com",
        password="another-secret-1234",
        full_name="Dr. Other",
    )
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor["email"], "password": other_doctor["password"]},
    )
    other_client_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    mine = await auth_client.get("/patients")
    theirs = await client.get("/patients", headers=other_client_headers)

    assert mine.status_code == 200
    assert len(mine.json()) == 1
    assert theirs.status_code == 200
    assert theirs.json() == []


async def test_get_patient_by_id(auth_client: AsyncClient):
    created = await create_patient(auth_client)

    response = await auth_client.get(f"/patients/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_nonexistent_patient_is_404(auth_client: AsyncClient):
    response = await auth_client.get("/patients/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_cannot_get_another_doctors_patient(
    auth_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    created = await create_patient(auth_client)

    other_doctor = await register_test_doctor(
        db_session,
        hospital_name="Other Hospital",
        email="second-doctor@example.com",
        password="another-secret-1234",
        full_name="Dr. Second",
    )
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor["email"], "password": other_doctor["password"]},
    )
    other_client_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/patients/{created['id']}", headers=other_client_headers)

    # Cross-tenant access returns 404, not 403 — the app never confirms to
    # one doctor that a given ID belongs to another doctor's patient.
    assert response.status_code == 404


async def test_replace_and_get_patient_hla_typings(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    entries = [
        {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        {"locus": "A", "allele_1": "29", "allele_2": "33"},
    ]

    put_response = await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=entries)
    get_response = await auth_client.get(f"/patients/{patient['id']}/hla-typings")

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    returned = {(e["locus"], e["allele_1"], e["allele_2"]) for e in get_response.json()}
    expected = {(e["locus"], e["allele_1"], e["allele_2"]) for e in entries}
    assert returned == expected


async def test_replace_and_get_patient_antibody_profiles(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    entries = [{"antigen": "B7", "mfi": 3500}]

    put_response = await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles", json=entries
    )
    get_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    assert len(get_response.json()) == 1
    assert get_response.json()[0]["antigen"] == "B7"


async def test_replace_antibody_profile_rejects_allele_level_antigen(auth_client: AsyncClient):
    # Regression: "B*44:02" (allele-level) can never match a donor's
    # serological typing ("B44") in the DSA check, so it used to be accepted
    # and saved without complaint, silently making a real DSA invisible.
    # See app/schemas/antibody_profile.py's validator.
    patient = await create_patient(auth_client)
    entries = [{"antigen": "B*44:02", "mfi": 12000}]

    put_response = await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles", json=entries
    )

    assert put_response.status_code == 422
    assert "serological designation" in put_response.text


async def test_create_and_list_sensitization_events(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    entries = [{"event_type": "pregnancy", "event_date": "2020-01-01"}]

    create_response = await auth_client.post(
        f"/patients/{patient['id']}/sensitization-events", json=entries
    )
    list_response = await auth_client.get(f"/patients/{patient['id']}/sensitization-events")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["event_type"] == "pregnancy"


async def test_get_patient_reports_empty_before_any_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await auth_client.get(f"/patients/{patient['id']}/reports")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------
# Update patient details — full_name/date_of_birth/nic_number only;
# blood_type/rh_factor are permanent once set.
# ---------------------------------------------------------------------


async def test_update_patient_details(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={
            "full_name": "Alice Renamed",
            "date_of_birth": "1986-07-16",
            "nic_number": "200000000006",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Alice Renamed"
    assert body["date_of_birth"] == "1986-07-16"
    assert body["nic_number"] == "200000000006"


async def test_update_patient_details_ignores_blood_type_and_rh_factor(
    auth_client: AsyncClient,
):
    patient = await create_patient(auth_client)  # blood_type=AB, rh_factor=+

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={
            "full_name": "Alice Patient",
            "date_of_birth": "1985-06-15",
            "blood_type": "O",
            "rh_factor": "-",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["blood_type"] == "AB"
    assert body["rh_factor"] == "+"


async def test_update_nonexistent_patient_is_404(auth_client: AsyncClient):
    response = await auth_client.put(
        "/patients/00000000-0000-0000-0000-000000000000",
        json={"full_name": "Nobody", "date_of_birth": "2000-01-01"},
    )

    assert response.status_code == 404


async def test_cannot_update_another_doctors_patient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(second_auth_client)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={"full_name": "Hijacked", "date_of_birth": "2000-01-01"},
    )

    assert response.status_code == 404


async def test_update_patient_details_rejects_missing_required_fields(
    auth_client: AsyncClient,
):
    patient = await create_patient(auth_client)

    response = await auth_client.put(
        f"/patients/{patient['id']}", json={"full_name": "Incomplete"}
    )

    assert response.status_code == 422


async def test_update_patient_details_writes_audit_log_entry(
    auth_client: AsyncClient, db_session
):
    patient = await create_patient(auth_client)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={"full_name": "Alice Renamed", "date_of_birth": "1985-06-15"},
    )
    assert response.status_code == 200

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "updated_patient_details")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["full_name"] == "Alice Renamed"


# ---------------------------------------------------------------------
# Delete patient — soft delete: the row survives, but disappears from
# every doctor-facing read path (get-by-id, list).
# ---------------------------------------------------------------------


async def test_delete_patient(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await auth_client.delete(f"/patients/{patient['id']}")
    assert response.status_code == 204

    get_response = await auth_client.get(f"/patients/{patient['id']}")
    assert get_response.status_code == 404

    list_response = await auth_client.get("/patients")
    assert list_response.json() == []


async def test_delete_patient_requires_auth(auth_client: AsyncClient):
    # auth_client wraps the same underlying httpx client as the plain
    # `client` fixture (auth_client just sets the header on it), so drop
    # the header rather than taking `client` as a separate param.
    patient = await create_patient(auth_client)
    del auth_client.headers["Authorization"]

    response = await auth_client.delete(f"/patients/{patient['id']}")

    assert response.status_code in (401, 403)


async def test_delete_nonexistent_patient_is_404(auth_client: AsyncClient):
    response = await auth_client.delete("/patients/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_cannot_delete_another_doctors_patient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(second_auth_client)

    response = await auth_client.delete(f"/patients/{patient['id']}")
    assert response.status_code == 404

    # Confirm it's still there for its actual owner (deletion didn't happen).
    get_response = await second_auth_client.get(f"/patients/{patient['id']}")
    assert get_response.status_code == 200


async def test_delete_patient_is_not_idempotent(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    first = await auth_client.delete(f"/patients/{patient['id']}")
    assert first.status_code == 204

    second = await auth_client.delete(f"/patients/{patient['id']}")
    assert second.status_code == 404


async def test_delete_patient_writes_audit_log_entry(auth_client: AsyncClient, db_session):
    patient = await create_patient(auth_client)

    response = await auth_client.delete(f"/patients/{patient['id']}")
    assert response.status_code == 204

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "deleted_patient")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["full_name"] == patient["full_name"]


async def test_update_patient_details_verified_omitted_preserves_true(auth_client: AsyncClient):
    # E2.1: PatientUpdate.details_verified=None ("no claim being made")
    # must preserve the record's current value, never reset it -- same
    # _resolve_verified contract as ocr_verified on PUT .../hla-typings.
    # A brand-new patient starts details_verified=True (manual entry).
    patient = await create_patient(auth_client)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={"full_name": "Alice Patient", "date_of_birth": "1985-06-15"},
    )

    assert response.status_code == 200
    assert response.json()["details_verified"] is True


async def test_update_patient_details_verified_omitted_preserves_false(auth_client: AsyncClient):
    # The regression case: a linked record whose details came from an
    # unconfirmed OCR extraction (details_verified=False) must NOT silently
    # flip back to trusted just because a later PUT omits the field.
    patient = await create_patient(auth_client, details_verified=False)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={"full_name": "Alice Patient", "date_of_birth": "1985-06-15"},
    )

    assert response.status_code == 200
    assert response.json()["details_verified"] is False


async def test_update_patient_details_verified_explicit_true_confirms_it(auth_client: AsyncClient):
    patient = await create_patient(auth_client, details_verified=False)

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={
            "full_name": "Alice Patient",
            "date_of_birth": "1985-06-15",
            "details_verified": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["details_verified"] is True


async def test_update_patient_preserves_sex_and_weight_when_omitted_is_still_a_real_reset(
    auth_client: AsyncClient,
):
    # PatientUpdate is a full-replace schema, not a partial patch -- sex/
    # weight_kg default to None if the caller doesn't send them. This is
    # intentional (see compatibilityWizard.js's buildPatientUpdatePayload,
    # which always carries the linked record's current values through), but
    # a bare PUT that omits them really does clear them -- documenting that
    # contract here so it can't silently change later.
    patient = await create_patient(auth_client, sex="female", weight_kg=60)
    assert patient["sex"] == "female"

    response = await auth_client.put(
        f"/patients/{patient['id']}",
        json={"full_name": "Alice Patient", "date_of_birth": "1985-06-15"},
    )

    assert response.status_code == 200
    assert response.json()["sex"] is None
    assert response.json()["weight_kg"] is None


# ---------------------------------------------------------------------
# PUT .../sensitization-events — replace semantics, unlike the additive
# POST above. See app/services/sensitization_event_service.py.
# ---------------------------------------------------------------------


async def test_replace_sensitization_events_is_idempotent(auth_client: AsyncClient):
    # Regression test for the doubling bug (Part E2.2): re-submitting the
    # same event set via PUT must leave exactly one row per event type, not
    # accumulate duplicates the way the additive POST would.
    patient = await create_patient(auth_client)
    entries = [{"event_type": "pregnancy", "event_date": "2020-01-01"}]

    first = await auth_client.put(f"/patients/{patient['id']}/sensitization-events", json=entries)
    second = await auth_client.put(f"/patients/{patient['id']}/sensitization-events", json=entries)

    assert first.status_code == 200
    assert second.status_code == 200

    list_response = await auth_client.get(f"/patients/{patient['id']}/sensitization-events")
    assert len(list_response.json()) == 1


async def test_replace_sensitization_events_with_empty_list_clears_them(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/sensitization-events",
        json=[{"event_type": "pregnancy", "event_date": "2020-01-01"}],
    )

    response = await auth_client.put(f"/patients/{patient['id']}/sensitization-events", json=[])

    assert response.status_code == 200
    assert response.json() == []

    list_response = await auth_client.get(f"/patients/{patient['id']}/sensitization-events")
    assert list_response.json() == []


async def test_deleted_patients_nic_number_can_be_reused(auth_client: AsyncClient):
    # Found 2026-08-04: the (doctor_id, nic_number) unique constraint used
    # to apply to every row regardless of is_deleted, so re-registering a
    # real person after their old record was deleted hit a false-positive
    # "already have a patient with this NIC number" 409.
    patient = await create_patient(auth_client, nic_number="912345678v")

    delete_response = await auth_client.delete(f"/patients/{patient['id']}")
    assert delete_response.status_code == 204

    response = await auth_client.post(
        "/patients", json=make_patient_payload(nic_number="912345678v")
    )
    assert response.status_code == 201
