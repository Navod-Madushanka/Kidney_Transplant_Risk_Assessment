# app/tests/integration/test_patients.py
from httpx import AsyncClient

from app.tests.conftest import create_patient, make_patient_payload


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


async def test_list_patients_returns_only_this_doctors_patients(
    auth_client: AsyncClient, client: AsyncClient
):
    await create_patient(auth_client, full_name="Doctor A's Patient")

    # A second doctor, registered independently, should see an empty list —
    # patients are scoped per doctor, not shared across the hospital.
    other_doctor_payload = {
        "hospital_name": "Other Hospital",
        "email": "other-doctor@example.com",
        "password": "another-secret-1234",
        "full_name": "Dr. Other",
    }
    await client.post("/auth/register", json=other_doctor_payload)
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor_payload["email"], "password": other_doctor_payload["password"]},
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


async def test_cannot_get_another_doctors_patient(auth_client: AsyncClient, client: AsyncClient):
    created = await create_patient(auth_client)

    other_doctor_payload = {
        "hospital_name": "Other Hospital",
        "email": "second-doctor@example.com",
        "password": "another-secret-1234",
        "full_name": "Dr. Second",
    }
    await client.post("/auth/register", json=other_doctor_payload)
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor_payload["email"], "password": other_doctor_payload["password"]},
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
