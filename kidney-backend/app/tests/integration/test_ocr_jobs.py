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

from app.services import ocr_batch_service

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
    async def _fake(file_bytes, filename, content_type, document_type):
        return responses_by_document_type[document_type]

    return _fake


def _fake_call_ocr_service_stream(structured_by_document_type, total_tiles=3):
    # Mirrors ocr-service's real /extract/stream contract (see ocr-service's
    # extract_bead_specificity_stream): progress events completed=0..total,
    # then one final result event.
    async def _fake(file_bytes, filename, content_type, document_type):
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
    async def _fake(file_bytes, filename, content_type, document_type):
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
