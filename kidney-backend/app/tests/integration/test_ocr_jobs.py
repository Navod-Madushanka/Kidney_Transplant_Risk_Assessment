# app/tests/integration/test_ocr_jobs.py
"""
Coverage for the document-extraction background job endpoints
(POST /ocr/extract-batch/jobs, GET /ocr/extract-batch/jobs/{id}) that
replaced the old /ocr/extract-batch/stream NDJSON endpoint -- see
app/services/ocr_job_service.py's module docstring for why: a doctor
navigating away from the photo-upload step mid-extraction used to kill
every visible sign of progress even though the fetch kept running
headless, and any result that arrived afterward wrote into the wizard with
no visible confirmation. A job row means extraction runs and reports
progress server-side regardless of what the browser does.

Mocks ocr_batch_service.call_ocr_service the same way
app/tests/unit/test_ocr_batch_service.py does, so this never needs a live
ocr-service/Ollama instance. Uses the real Postgres test DB (via the
auth_client/db_session fixtures in conftest.py) since the whole point here
is the job row's persistence and doctor-scoping.
"""
import asyncio

from httpx import AsyncClient
from sqlalchemy import select

from app.models.ocr_extraction_job import OcrExtractionJob
from app.services import ocr_batch_service, ocr_job_service
from app.tests.conftest import create_patient

HLA_TYPING_RESPONSE = {
    "structured": {
        "patient_details": {"full_name": "Rev.A.Premarathna Thero", "nic_number": "198001610076"},
        "donor_details": {"full_name": "K.R.Bandara", "nic_number": "823275544v"},
        "patient_hla": [{"locus": "A", "allele_1": "29", "allele_2": "33"}],
        "donor_hla": [],
    }
}
FAKE_IMAGE = ("hla.jpg", b"fake-bytes", "image/jpeg")


def _fake_call_ocr_service(responses_by_document_type):
    # Part G bounded-memory pass: call_ocr_service/call_ocr_service_stream
    # now take a SpooledUpload (the real code path spools every upload to
    # local disk before this is ever called -- see
    # app/services/ocr_spool_service.py), not raw bytes.
    async def _fake(upload, document_type):
        return responses_by_document_type[document_type]

    return _fake


def _fake_call_ocr_service_stream(structured_by_document_type, total_tiles=3):
    # Mirrors ocr-service's real /extract/stream contract (see ocr-service's
    # extract_bead_specificity_stream): progress events completed=0..total,
    # then one final result event.
    async def _fake(upload, document_type):
        for completed in range(total_tiles + 1):
            yield {"type": "progress", "completed": completed, "total": total_tiles}
        yield {
            "type": "result",
            "document_type": document_type,
            "structured": structured_by_document_type[document_type],
        }

    return _fake


async def _await_job_done(auth_client: AsyncClient, job_id: str, attempts: int = 20, delay: float = 0.05) -> dict:
    # Starlette's BackgroundTasks actually run to completion inside the
    # same await as the triggering request when driven through an
    # ASGITransport-based test client (no real network hop to defer past),
    # so in practice the very first poll already sees a terminal status --
    # this loop is just a safety net against relying on that timing detail.
    body = {}
    for _ in range(attempts):
        response = await auth_client.get(f"/ocr/extract-batch/jobs/{job_id}")
        body = response.json()
        if body["status"] != "running":
            return body
        await asyncio.sleep(delay)
    return body


async def test_start_job_returns_job_id_immediately(monkeypatch, auth_client: AsyncClient):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service({"hla_typing_report": HLA_TYPING_RESPONSE}),
    )

    response = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )

    assert response.status_code == 202
    assert "job_id" in response.json()


async def test_start_job_without_any_file_returns_400(auth_client: AsyncClient):
    response = await auth_client.post("/ocr/extract-batch/jobs")
    assert response.status_code == 400


async def test_job_reaches_done_with_hydrated_data(monkeypatch, auth_client: AsyncClient):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service({"hla_typing_report": HLA_TYPING_RESPONSE}),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"
    doc = body["documents"]["hla_typing_report"]
    assert doc["status"] == "done"
    assert doc["completed"] == doc["total"]
    assert doc["patient_details"]["full_name"] == "Rev.A.Premarathna Thero"
    assert doc["patient_hla"] == [{"locus": "A", "allele_1": "29", "allele_2": "33"}]


async def test_document_level_failure_does_not_fail_whole_job(monkeypatch, auth_client: AsyncClient):
    # Regression guard: one document's OCR call blowing up must still let
    # the job (and any other document in the same batch) reach "done" --
    # matching stream_batch_extraction's existing per-document error
    # tolerance, now carried through the job row instead of an NDJSON line.
    async def _fake(upload, document_type):
        raise RuntimeError("Ollama unreachable")

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _fake)

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"
    doc = body["documents"]["hla_typing_report"]
    assert doc["status"] == "done"
    assert doc["errors"] == [
        {"field": "hla_typing_report", "message": "OCR failed: Ollama unreachable"}
    ]
    assert doc["patient_details"]["full_name"] == ""


async def test_bead_specificity_progress_reaches_total_on_completion(
    monkeypatch, auth_client: AsyncClient
):
    # The one document type with real intermediate progress (8 sequential
    # tile calls on a real page -- 3 here for a smaller fixture) -- confirms
    # ProgressEvents from ocr_batch_service.stream_batch_extraction land in
    # the job row's completed/total fields, not just the final result.
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": {"bead_specificity": [{"antigen": "A23", "mfi": 490.5}]}},
            total_tiles=3,
        ),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"bead_specificity_page_1": FAKE_IMAGE},
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"
    doc = body["documents"]["bead_specificity_page_1"]
    assert doc["status"] == "done"
    assert doc["total"] == 3
    assert doc["completed"] == 3
    assert doc["bead_specificity"] == [{"antigen": "A23", "mfi": 490.5}]


async def test_job_not_visible_to_a_different_doctor(
    monkeypatch, auth_client: AsyncClient, second_auth_client: AsyncClient
):
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service",
        _fake_call_ocr_service({"hla_typing_report": HLA_TYPING_RESPONSE}),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    other_doctor_response = await second_auth_client.get(f"/ocr/extract-batch/jobs/{job_id}")
    assert other_doctor_response.status_code == 404

    owner_response = await auth_client.get(f"/ocr/extract-batch/jobs/{job_id}")
    assert owner_response.status_code == 200


async def test_get_unknown_job_returns_404(auth_client: AsyncClient):
    response = await auth_client.get(
        "/ocr/extract-batch/jobs/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


def _fake_call_ocr_service_stream_by_filename(structured_by_filename, total_tiles=1):
    # Unlike _fake_call_ocr_service_stream above (keyed by document_type),
    # both bead-specificity pages map to the SAME document_type
    # ("bead_specificity" -- see SLOT_DOCUMENT_TYPES), so a fake keyed by
    # document_type can't return different rows per page. Keying by
    # filename instead lets these tests prove page 1's and page 2's rows
    # both land in the saved profile (concatenated), not just one of them.
    # Note the filename here is upload.filename -- the SERVER-generated
    # spool filename (slot name + extension), not whatever the client
    # named the file in the multipart request; see ocr_spool_service.py.
    async def _fake(upload, document_type):
        for completed in range(total_tiles + 1):
            yield {"type": "progress", "completed": completed, "total": total_tiles}
        yield {
            "type": "result",
            "document_type": document_type,
            "structured": structured_by_filename[upload.filename],
        }

    return _fake


async def test_bead_specificity_job_with_patient_id_saves_unverified_profiles(
    monkeypatch, auth_client: AsyncClient
):
    patient = await create_patient(auth_client)
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream_by_filename(
            {
                "bead_specificity_page_1.jpg": {
                    "bead_specificity": [{"antigen": "A1", "mfi": 1000}]
                },
                "bead_specificity_page_2.jpg": {
                    "bead_specificity": [{"antigen": "B7", "mfi": 2500}]
                },
            }
        ),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={
            "bead_specificity_page_1": ("page1.jpg", b"fake-bytes", "image/jpeg"),
            "bead_specificity_page_2": ("page2.jpg", b"fake-bytes", "image/jpeg"),
        },
        data={"patient_id": patient["id"]},
    )
    assert start.status_code == 202
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)
    assert body["status"] == "done"

    profiles_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")
    profiles = {(p["antigen"], float(p["mfi"])) for p in profiles_response.json()}
    assert profiles == {("A1", 1000.0), ("B7", 2500.0)}

    patient_response = await auth_client.get(f"/patients/{patient['id']}")
    assert patient_response.json()["antibody_profile_verified"] is False


async def test_job_with_patient_id_from_another_doctor_returns_404(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(second_auth_client)

    response = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"bead_specificity_page_1": FAKE_IMAGE},
        data={"patient_id": patient["id"]},
    )

    assert response.status_code == 404


async def test_job_without_patient_id_does_not_touch_antibody_profiles(
    monkeypatch, auth_client: AsyncClient
):
    patient = await create_patient(auth_client)
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": {"bead_specificity": [{"antigen": "A23", "mfi": 490.5}]}},
        ),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"bead_specificity_page_1": FAKE_IMAGE},
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)
    assert body["status"] == "done"

    profiles_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")
    assert profiles_response.json() == []
    patient_response = await auth_client.get(f"/patients/{patient['id']}")
    assert patient_response.json()["antibody_profile_verified"] is True


async def test_get_job_without_auth_returns_401(client: AsyncClient):
    # `client` alone (no Authorization header) -- confirms the route
    # requires auth at all, before doctor-scoping is even considered.
    # (Not combined with auth_client in the same test: that fixture just
    # adds a header onto this same `client` instance in place, so
    # requesting both would silently test an already-authenticated client.)
    response = await client.get(
        "/ocr/extract-batch/jobs/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------
# Spool lifecycle (Part G, bounded memory for the extraction upload path)
# -- uploads are spooled to local disk before the job row is even
# created, and app/services/ocr_job_service.py's run_extraction_job
# discards the whole spool directory in a try/finally around the entire
# job body, on every path out (done, per-document error, or a genuine
# job-level exception). See app/services/ocr_spool_service.py.
# ---------------------------------------------------------------------


async def test_spool_directory_exists_during_job_and_is_removed_after(
    monkeypatch, auth_client: AsyncClient
):
    captured_spool_dir = {}

    async def _fake(upload, document_type):
        # Captured from inside the extraction call itself -- Starlette's
        # BackgroundTasks run to completion inline for an ASGITransport-
        # driven test client, so this is the only window in which the
        # spool directory is actually observable as still present.
        captured_spool_dir["path"] = upload.path.parent
        assert upload.path.exists()
        assert upload.path.parent.exists()
        return HLA_TYPING_RESPONSE

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _fake)

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"
    assert "path" in captured_spool_dir
    # Discarded once the job (and its try/finally) has finished.
    assert not captured_spool_dir["path"].exists()


async def test_job_level_failure_still_cleans_up_its_spool(monkeypatch, auth_client: AsyncClient):
    # Per-document OCR failures are already caught inside
    # stream_batch_extraction and don't fail the whole job (see
    # test_document_level_failure_does_not_fail_whole_job above) -- to
    # exercise run_extraction_job's own last-resort except (job.status =
    # FAILED), this breaks stream_batch_extraction itself, one layer up
    # from where that per-document tolerance lives.
    captured_spool_dir = {}

    async def _broken_stream(files):
        captured_spool_dir["path"] = files["hla_typing_report"].path.parent
        raise RuntimeError("boom")
        yield  # pragma: no cover -- makes this an async generator

    monkeypatch.setattr(ocr_job_service, "stream_batch_extraction", _broken_stream)

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "failed"
    assert body["error"] == "boom"
    assert "path" in captured_spool_dir
    assert not captured_spool_dir["path"].exists()


async def test_oversized_upload_returns_413_with_no_job_row_created(
    auth_client: AsyncClient, db_session
):
    # OCR_UPLOAD_MAX_SIZE_MB is set to 1 in conftest for exactly this test.
    oversized = b"x" * (2 * 1024 * 1024)

    response = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"hla_typing_report": ("big.jpg", oversized, "image/jpeg")},
    )

    assert response.status_code == 413

    result = await db_session.execute(select(OcrExtractionJob))
    assert result.scalars().all() == []
