# app/tests/integration/test_donors.py
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.tests.conftest import create_donor, make_donor_payload


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
