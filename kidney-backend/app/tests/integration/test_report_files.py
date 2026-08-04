# app/tests/integration/test_report_files.py
"""
Coverage for report-file attachments (app/services/report_file_service.py,
the /patients/{id}/report-files and /donors/{id}/report-files routes) — a
plain reference-document archive, not the OCR pipeline. Patient routes get
full coverage; donor routes get a lighter mirror since the underlying
service/route code is a deliberate twin of the patient path.
"""
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.tests.conftest import create_donor, create_patient

PDF_BYTES = b"%PDF-1.4 fake report bytes for testing"


async def _upload(client: AsyncClient, entity: str, entity_id: str, **overrides):
    data = {"category": overrides.get("category", "hla_typing_report")}
    filename = overrides.get("filename", "report.pdf")
    content = overrides.get("content", PDF_BYTES)
    content_type = overrides.get("content_type", "application/pdf")
    return await client.post(
        f"/{entity}/{entity_id}/report-files",
        data=data,
        files={"file": (filename, content, content_type)},
    )


# ---------------------------------------------------------------------
# Patient report files — full coverage
# ---------------------------------------------------------------------


async def test_upload_patient_report_file(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await _upload(auth_client, "patients", patient["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "hla_typing_report"
    assert body["original_filename"] == "report.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert "id" in body


async def test_upload_writes_audit_log_entry(auth_client: AsyncClient, db_session):
    patient = await create_patient(auth_client)

    response = await _upload(auth_client, "patients", patient["id"])
    assert response.status_code == 201

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "uploaded_patient_report_file")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["original_filename"] == "report.pdf"


async def test_upload_rejects_unsupported_content_type(auth_client: AsyncClient):
    patient = await create_patient(auth_client)

    response = await _upload(
        auth_client, "patients", patient["id"],
        filename="notes.txt", content=b"plain text", content_type="text/plain",
    )

    assert response.status_code == 415


async def test_upload_rejects_oversized_file(auth_client: AsyncClient):
    # REPORT_FILES_MAX_SIZE_MB is set to 1 in conftest for exactly this test.
    patient = await create_patient(auth_client)
    oversized = b"x" * (2 * 1024 * 1024)

    response = await _upload(auth_client, "patients", patient["id"], content=oversized)

    assert response.status_code == 413


async def test_upload_requires_own_patient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    other_patient = await create_patient(second_auth_client)

    response = await _upload(auth_client, "patients", other_patient["id"])

    assert response.status_code == 404


async def test_list_returns_only_this_doctors_files(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(auth_client)
    await _upload(auth_client, "patients", patient["id"])

    response = await auth_client.get(f"/patients/{patient['id']}/report-files")
    assert response.status_code == 200
    assert len(response.json()) == 1

    other_patient = await create_patient(second_auth_client)
    response = await auth_client.get(f"/patients/{other_patient['id']}/report-files")
    assert response.status_code == 404


async def test_download_returns_correct_bytes_and_filename(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"], filename="typing.pdf")
    file_id = upload.json()["id"]

    response = await auth_client.get(f"/patients/{patient['id']}/report-files/{file_id}/download")

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"
    assert "typing.pdf" in response.headers["content-disposition"]


async def test_delete_removes_db_row_and_file_on_disk(auth_client: AsyncClient, db_session):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"])
    file_id = upload.json()["id"]

    settings = get_settings()
    absolute_path = Path(settings.report_files_storage_dir) / f"patients/{patient['id']}"
    on_disk_before = list(absolute_path.glob("*"))
    assert len(on_disk_before) == 1

    response = await auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")

    assert response.status_code == 204
    assert list(absolute_path.glob("*")) == []

    list_response = await auth_client.get(f"/patients/{patient['id']}/report-files")
    assert list_response.json() == []


async def test_delete_when_file_already_missing_from_disk_still_succeeds(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"])
    file_id = upload.json()["id"]

    settings = get_settings()
    absolute_path = Path(settings.report_files_storage_dir) / f"patients/{patient['id']}"
    for f in absolute_path.glob("*"):
        f.unlink()

    response = await auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")

    assert response.status_code == 204


async def test_delete_twice_is_not_idempotent(auth_client: AsyncClient):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"])
    file_id = upload.json()["id"]

    first = await auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")
    second = await auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")

    assert first.status_code == 204
    assert second.status_code == 404


async def test_delete_writes_audit_log_entry(auth_client: AsyncClient, db_session):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"])
    file_id = upload.json()["id"]

    await auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "deleted_patient_report_file")
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].details["original_filename"] == "report.pdf"


async def test_download_and_delete_require_own_patient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(auth_client)
    upload = await _upload(auth_client, "patients", patient["id"])
    file_id = upload.json()["id"]

    download = await second_auth_client.get(
        f"/patients/{patient['id']}/report-files/{file_id}/download"
    )
    delete = await second_auth_client.delete(f"/patients/{patient['id']}/report-files/{file_id}")

    assert download.status_code == 404
    assert delete.status_code == 404


# ---------------------------------------------------------------------
# Donor report files — lighter mirror
# ---------------------------------------------------------------------


async def test_upload_list_download_delete_donor_report_file(auth_client: AsyncClient):
    donor = await create_donor(auth_client)

    upload = await _upload(auth_client, "donors", donor["id"], category="crossmatch_report")
    assert upload.status_code == 201
    file_id = upload.json()["id"]
    assert upload.json()["category"] == "crossmatch_report"

    listed = await auth_client.get(f"/donors/{donor['id']}/report-files")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    downloaded = await auth_client.get(f"/donors/{donor['id']}/report-files/{file_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES

    deleted = await auth_client.delete(f"/donors/{donor['id']}/report-files/{file_id}")
    assert deleted.status_code == 204


async def test_donor_report_file_routes_require_ownership(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    donor = await create_donor(second_auth_client)

    upload = await _upload(auth_client, "donors", donor["id"])
    list_response = await auth_client.get(f"/donors/{donor['id']}/report-files")

    assert upload.status_code == 404
    assert list_response.status_code == 404
