# app/tests/integration/test_donors.py
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.tests.conftest import create_donor, create_patient, make_donor_payload


async def test_create_donor(auth_client: AsyncClient):
    response = await auth_client.post("/donors", json=make_donor_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Bob Donor"
    assert body["blood_type"] == "O"
    assert "id" in body


async def test_create_donor_requires_auth(client: AsyncClient):
    response = await client.post("/donors", json=make_donor_payload())

    assert response.status_code in (401, 403)


async def test_list_donors_returns_only_this_doctors_donors(auth_client: AsyncClient):
    await create_donor(auth_client)
    await create_donor(auth_client, full_name="Second Donor")

    response = await auth_client.get("/donors")

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_get_donor_by_id(auth_client: AsyncClient):
    created = await create_donor(auth_client)

    response = await auth_client.get(f"/donors/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_get_nonexistent_donor_is_404(auth_client: AsyncClient):
    response = await auth_client.get("/donors/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_duplicate_nic_across_doctors_returns_clean_conflict_not_500(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # Donor nic_number is deliberately kept GLOBALLY unique (unlike
    # patients, see test_patients.py's equivalent tests) -- donors already
    # have a real cross-hospital sharing path (the available-donor search),
    # so a shared NIC constraint guards against two hospitals registering
    # the same physical donor as two separate records. It used to crash
    # with an unhandled 500 (raw asyncpg.UniqueViolationError) instead of a
    # clean error (found 2026-08-03) -- confirm it's a clean 409 now, and
    # that the constraint itself is still global (second doctor is rejected).
    await create_donor(auth_client, nic_number="823275544v")

    response = await second_auth_client.post(
        "/donors", json=make_donor_payload(full_name="Someone Else", nic_number="823275544v")
    )

    assert response.status_code == 409


async def test_replace_and_get_donor_hla_typings(auth_client: AsyncClient):
    donor = await create_donor(auth_client)
    entries = [{"locus": "B", "allele_1": "40", "allele_2": "40"}]

    put_response = await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=entries)
    get_response = await auth_client.get(f"/donors/{donor['id']}/hla-typings")

    assert put_response.status_code == 204
    assert get_response.status_code == 200
    assert len(get_response.json()) == 1
    assert get_response.json()[0]["locus"] == "B"


async def test_replace_donor_hla_typings_for_nonexistent_donor_is_404(auth_client: AsyncClient):
    entries = [{"locus": "B", "allele_1": "40", "allele_2": "40"}]

    response = await auth_client.put(
        "/donors/00000000-0000-0000-0000-000000000000/hla-typings", json=entries
    )

    assert response.status_code == 404


async def test_new_donor_defaults_to_available_status(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    assert donor["status"] == "available"


async def test_update_donor_status(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    response = await auth_client.put(f"/donors/{donor['id']}/status", json={"status": "reserved"})

    assert response.status_code == 200
    assert response.json()["status"] == "reserved"

    get_response = await auth_client.get(f"/donors/{donor['id']}")
    assert get_response.json()["status"] == "reserved"


async def test_cannot_update_another_doctors_donor_status(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(second_auth_client)

    response = await auth_client.put(f"/donors/{donor['id']}/status", json={"status": "reserved"})

    assert response.status_code == 404


async def test_donor_status_accepts_the_newly_added_values(auth_client: AsyncClient):
    # Regression coverage for the 2026-08-08 fix: the enum used to only have
    # available/reserved/transplanted, leaving no way to record a donor
    # mid-workup, ruled out, or no longer participating.
    donor = await create_donor(auth_client)

    for new_status in ("under_workup", "medically_unfit", "withdrawn", "deceased"):
        response = await auth_client.put(
            f"/donors/{donor['id']}/status", json={"status": new_status}
        )
        assert response.status_code == 200
        assert response.json()["status"] == new_status


async def test_transplanted_donor_status_is_terminal(auth_client: AsyncClient):
    # Regression coverage for review #2 bug 7: every status used to accept
    # every other status unconditionally, so a transplanted donor could be
    # silently flipped back to "available" and re-enter cross-hospital
    # search/the exchange pool as a live organ.
    donor = await create_donor(auth_client)

    response = await auth_client.put(
        f"/donors/{donor['id']}/status", json={"status": "transplanted"}
    )
    assert response.status_code == 200

    response = await auth_client.put(
        f"/donors/{donor['id']}/status", json={"status": "available"}
    )
    assert response.status_code == 409

    get_response = await auth_client.get(f"/donors/{donor['id']}")
    assert get_response.json()["status"] == "transplanted"


async def test_deceased_donor_status_is_terminal(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    response = await auth_client.put(f"/donors/{donor['id']}/status", json={"status": "deceased"})
    assert response.status_code == 200

    response = await auth_client.put(
        f"/donors/{donor['id']}/status", json={"status": "available"}
    )
    assert response.status_code == 409


async def test_medically_unfit_donor_cannot_silently_become_available(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    response = await auth_client.put(
        f"/donors/{donor['id']}/status", json={"status": "medically_unfit"}
    )
    assert response.status_code == 200

    response = await auth_client.put(
        f"/donors/{donor['id']}/status", json={"status": "available"}
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------
# Update donor details — lighter mirror of the patient coverage in
# test_patients.py, since the service/route code is a deliberate twin.
# ---------------------------------------------------------------------


async def test_update_donor_details_ignores_blood_type_and_rh_factor(auth_client: AsyncClient):
    donor = await create_donor(auth_client)  # blood_type=O, rh_factor=+

    response = await auth_client.put(
        f"/donors/{donor['id']}",
        json={
            "full_name": "Bob Renamed",
            "date_of_birth": "1991-03-21",
            "nic_number": "199112345678",
            "blood_type": "AB",
            "rh_factor": "-",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Bob Renamed"
    assert body["date_of_birth"] == "1991-03-21"
    assert body["nic_number"] == "199112345678"
    assert body["blood_type"] == "O"
    assert body["rh_factor"] == "+"


async def test_create_and_update_donor_clinical_fields(auth_client: AsyncClient):
    response = await auth_client.post(
        "/donors",
        json=make_donor_payload(
            egfr=65.5, systolic_bp=130, diastolic_bp=85, bmi=24.3,
            has_diabetes=False, smoking_status="current",
            sex="male", race="black", creatinine=1.2, urine_acr=15.0,
            is_on_antihypertensive_medication=True,
            family_history_kidney_disease=False,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["egfr"] == 65.5
    assert body["systolic_bp"] == 130
    assert body["diastolic_bp"] == 85
    assert body["bmi"] == 24.3
    assert body["has_diabetes"] is False
    assert body["smoking_status"] == "current"
    assert body["sex"] == "male"
    assert body["race"] == "black"
    assert body["creatinine"] == 1.2
    assert body["urine_acr"] == 15.0
    assert body["is_on_antihypertensive_medication"] is True
    assert body["family_history_kidney_disease"] is False

    update_response = await auth_client.put(
        f"/donors/{body['id']}",
        json={
            "full_name": body["full_name"],
            "date_of_birth": body["date_of_birth"],
            "egfr": 58.0,
            "has_diabetes": None,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["egfr"] == 58.0
    # Fields omitted from the PUT payload fall back to the schema's
    # default (None) -- DonorUpdate isn't a partial/PATCH payload, it's the
    # full desired state, same as every other field on this endpoint.
    assert updated["has_diabetes"] is None
    assert updated["systolic_bp"] is None
    assert updated["smoking_status"] is None
    assert updated["sex"] is None


async def test_donor_created_without_clinical_fields_leaves_them_null(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    assert donor["egfr"] is None
    assert donor["has_diabetes"] is None
    assert donor["smoking_status"] is None
    assert donor["sex"] is None
    assert donor["race"] is None
    assert donor["creatinine"] is None
    assert donor["urine_acr"] is None
    assert donor["is_on_antihypertensive_medication"] is None
    assert donor["family_history_kidney_disease"] is None


async def test_donor_egfr_out_of_range_is_rejected(auth_client: AsyncClient):
    response = await auth_client.post("/donors", json=make_donor_payload(egfr=500))

    assert response.status_code == 422


async def test_cannot_update_another_doctors_donor_details(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(second_auth_client)

    response = await auth_client.put(
        f"/donors/{donor['id']}",
        json={"full_name": "Hijacked", "date_of_birth": "2000-01-01"},
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------
# Delete donor — soft delete: the row survives, but disappears from every
# doctor-facing read path (get-by-id, list, cross-hospital search).
# ---------------------------------------------------------------------


async def test_delete_donor(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    response = await auth_client.delete(f"/donors/{donor['id']}")
    assert response.status_code == 204

    get_response = await auth_client.get(f"/donors/{donor['id']}")
    assert get_response.status_code == 404

    list_response = await auth_client.get("/donors")
    assert list_response.json() == []


async def test_delete_donor_requires_auth(auth_client: AsyncClient):
    # auth_client wraps the same underlying httpx client as the plain
    # `client` fixture (auth_client just sets the header on it), so drop
    # the header rather than taking `client` as a separate param.
    donor = await create_donor(auth_client)
    del auth_client.headers["Authorization"]

    response = await auth_client.delete(f"/donors/{donor['id']}")

    assert response.status_code in (401, 403)


async def test_delete_nonexistent_donor_is_404(auth_client: AsyncClient):
    response = await auth_client.delete("/donors/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


async def test_cannot_delete_another_doctors_donor(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(second_auth_client)

    response = await auth_client.delete(f"/donors/{donor['id']}")
    assert response.status_code == 404

    # Confirm it's still there for its actual owner (deletion didn't happen).
    get_response = await second_auth_client.get(f"/donors/{donor['id']}")
    assert get_response.status_code == 200


async def test_delete_donor_is_not_idempotent(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    first = await auth_client.delete(f"/donors/{donor['id']}")
    assert first.status_code == 204

    second = await auth_client.delete(f"/donors/{donor['id']}")
    assert second.status_code == 404


async def test_delete_donor_writes_audit_log_entry(auth_client: AsyncClient, db_session):
    donor = await create_donor(auth_client)

    response = await auth_client.delete(f"/donors/{donor['id']}")
    assert response.status_code == 204

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "deleted_donor")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["full_name"] == donor["full_name"]


# ---------------------------------------------------------------------
# intended_recipient_id — a living donor committed to a specific patient
# rather than a free-floating pool organ. See donor_search_service.py and
# the Donor model's docstring comment on this field.
# ---------------------------------------------------------------------


async def test_create_donor_with_intended_recipient(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await auth_client.post(
        "/donors", json=make_donor_payload(intended_recipient_id=patient["id"])
    )

    assert response.status_code == 201
    assert response.json()["intended_recipient_id"] == patient["id"]


async def test_donor_created_without_intended_recipient_defaults_to_none(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    assert donor["intended_recipient_id"] is None


async def test_create_donor_rejects_another_doctors_patient_as_recipient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    other_patient = await create_patient(second_auth_client)

    response = await auth_client.post(
        "/donors", json=make_donor_payload(intended_recipient_id=other_patient["id"])
    )

    assert response.status_code == 404


async def test_create_donor_rejects_nonexistent_intended_recipient(auth_client: AsyncClient):
    response = await auth_client.post(
        "/donors",
        json=make_donor_payload(
            intended_recipient_id="00000000-0000-0000-0000-000000000000"
        ),
    )

    assert response.status_code == 404


async def test_update_donor_can_set_and_clear_intended_recipient(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    donor = await create_donor(auth_client)

    set_response = await auth_client.put(
        f"/donors/{donor['id']}",
        json={
            "full_name": donor["full_name"],
            "date_of_birth": donor["date_of_birth"],
            "intended_recipient_id": patient["id"],
        },
    )
    assert set_response.status_code == 200
    assert set_response.json()["intended_recipient_id"] == patient["id"]

    clear_response = await auth_client.put(
        f"/donors/{donor['id']}",
        json={"full_name": donor["full_name"], "date_of_birth": donor["date_of_birth"]},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["intended_recipient_id"] is None


async def test_update_donor_rejects_another_doctors_patient_as_recipient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(auth_client)
    other_patient = await create_patient(second_auth_client)

    response = await auth_client.put(
        f"/donors/{donor['id']}",
        json={
            "full_name": donor["full_name"],
            "date_of_birth": donor["date_of_birth"],
            "intended_recipient_id": other_patient["id"],
        },
    )

    assert response.status_code == 404


async def test_deleted_donors_nic_number_can_be_reused(auth_client: AsyncClient):
    # Found 2026-08-04: the global unique index on nic_number used to apply
    # to every row regardless of is_deleted, so re-registering a real donor
    # after their old record was deleted hit a false-positive "already
    # registered" 409.
    donor = await create_donor(auth_client, nic_number="823275544v")

    delete_response = await auth_client.delete(f"/donors/{donor['id']}")
    assert delete_response.status_code == 204

    response = await auth_client.post(
        "/donors", json=make_donor_payload(nic_number="823275544v")
    )
    assert response.status_code == 201
