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

from app.models.audit_log import AuditLog
from app.models.ocr_extraction_job import OcrExtractionJob
from app.services import ocr_batch_service, ocr_job_service
from app.tests.conftest import create_patient

HLA_TYPING_RESPONSE = {
    "structured": {
        "patient_details": {"full_name": "Rev.S.Amarasinghe Thero", "nic_number": "198723456789"},
        "donor_details": {"full_name": "K.R.Wickremasinghe", "nic_number": "852741963v"},
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
    # **kwargs absorbs extra_data (dsa_band_edges) -- see the real
    # call_ocr_service_stream's signature; this fake doesn't need it.
    async def _fake(upload, document_type, **kwargs):
        for completed in range(total_tiles + 1):
            yield {"type": "progress", "completed": completed, "total": total_tiles}
        yield {
            "type": "result",
            "document_type": document_type,
            "structured": structured_by_document_type[document_type],
        }

    return _fake


async def _await_job_done(auth_client: AsyncClient, job_id: str, attempts: int = 20, delay: float = 0.05) -> dict:
    # The job is scheduled via asyncio.create_task, not FastAPI's
    # BackgroundTasks (see ocr_job_service.schedule_extraction_job's
    # docstring for why) -- so unlike a BackgroundTasks-driven job, the
    # POST that starts it returns before the job coroutine has necessarily
    # run at all, let alone finished. This loop is load-bearing, not a
    # safety net: with the fakes below resolving near-instantly, the job
    # is normally done within the first couple of polls.
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
    assert doc["patient_details"]["full_name"] == "Rev.S.Amarasinghe Thero"
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
    # page/panel stamped from the slot (bead_specificity_page_1 -> page
    # 1/class_i, see SLOT_PAGE_PANEL); bead/conflict are None since the
    # fake response doesn't set a bead ID.
    assert doc["bead_specificity"] == [
        {
            "bead": None,
            "antigen": "A23",
            "mfi": 490.5,
            "page": 1,
            "panel": "class_i",
            "conflict": None,
        }
    ]


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
    # **kwargs absorbs extra_data (dsa_band_edges).
    async def _fake(upload, document_type, **kwargs):
        for completed in range(total_tiles + 1):
            yield {"type": "progress", "completed": completed, "total": total_tiles}
        yield {
            "type": "result",
            "document_type": document_type,
            "structured": structured_by_filename[upload.filename],
        }

    return _fake


async def test_bead_specificity_job_with_patient_id_saves_unverified_profiles(
    monkeypatch, auth_client: AsyncClient, db_session
):
    # Restored after Part J (J0-J3) deleted the original, unguarded
    # version of this auto-save entirely, then a later live-test round
    # asked for it back with the guard kept: a fresh patient (the only
    # kind NewPairPage.jsx ever passes here) has no existing rows to
    # protect, so the save proceeds -- see
    # _save_bead_specificity_if_present's docstring for why the guard is
    # keyed on existing rows, not the antibody_profile_verified flag
    # (which defaults True on every new patient).
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

    # Audit provenance (J5): distinguishable from a doctor typing it in.
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "replaced_patient_antibody_profiles")
    )
    entry = result.scalar_one()
    assert entry.details["source"] == "ocr_job"
    assert entry.details["job_id"] == job_id


async def test_existing_profile_is_untouched_by_a_completed_extraction_job(
    monkeypatch, auth_client: AsyncClient
):
    # The scenario that made the original auto-save dangerous: a doctor
    # with an already-verified, hand-checked profile has a bead-
    # specificity extraction job started against that same patient later.
    # The unguarded version hard-deleted the verified rows the moment the
    # job finished and flipped antibody_profile_verified back to False,
    # silently ejecting the patient from the exchange pool. The guard
    # restored here keys on existing rows (verified or not), not the
    # verified flag alone -- see _save_bead_specificity_if_present's
    # docstring for why.
    patient = await create_patient(auth_client)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles?ocr_verified=true",
        json=[{"antigen": "A2", "mfi": 3500}],
    )

    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {"bead_specificity": {"bead_specificity": [{"antigen": "B7", "mfi": 2500}]}},
        ),
    )
    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"bead_specificity_page_1": FAKE_IMAGE},
        data={"patient_id": patient["id"]},
    )
    job_id = start.json()["job_id"]
    body = await _await_job_done(auth_client, job_id)
    assert body["status"] == "done"

    profiles_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")
    profiles = {(p["antigen"], float(p["mfi"])) for p in profiles_response.json()}
    assert profiles == {("A2", 3500.0)}  # the verified row survives, untouched

    patient_response = await auth_client.get(f"/patients/{patient['id']}")
    assert patient_response.json()["antibody_profile_verified"] is True  # still verified

    # The doctor learns WHY nothing was saved, rather than the extraction
    # just silently going nowhere.
    doc = body["documents"]["bead_specificity_page_1"]
    assert any("already has an antibody profile on file" in e["message"] for e in doc["errors"])


async def test_null_mfi_row_is_filtered_from_auto_save_without_failing_the_job(
    monkeypatch, auth_client: AsyncClient
):
    # Part I (I8): the prompt deliberately preserves an illegible row as
    # mfi=None instead of dropping it (a doctor can spot-check a flagged
    # null far more easily than notice a row that was silently never
    # mentioned). AntibodyProfile.mfi is NOT NULL, so building an entry
    # straight from that row used to raise a validation error that failed
    # the WHOLE job -- taking every other successfully-extracted document
    # down with it. This is the regression test for that crash.
    patient = await create_patient(auth_client)
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream(
            {
                "bead_specificity": {
                    "bead_specificity": [
                        {"bead": "010", "antigen": "A23", "mfi": 23706.91},
                        {"bead": "011", "antigen": "A24", "mfi": None},
                    ]
                }
            },
        ),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={"bead_specificity_page_1": FAKE_IMAGE},
        data={"patient_id": patient["id"]},
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"  # NOT "failed"

    profiles_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")
    profiles = profiles_response.json()
    assert len(profiles) == 1  # only the readable row was saved
    assert profiles[0]["bead_id"] == "010"


async def test_cross_page_bead_id_collision_survives_as_distinct_rows(
    monkeypatch, auth_client: AsyncClient
):
    # Real-chart case (Part I, I7): bead 044 is B76,Bw6 on page 1 (Class
    # I) and DQ4 on page 2 (Class II) -- each page's panel is numbered
    # from 001 independently, so (page, bead), not bead alone, is the
    # real identity once both pages are merged. Cross-page merging must
    # NOT collapse these into one row -- checked both via job.documents
    # (what a doctor reviewing the extraction sees) and via the saved
    # profile (what actually persists).
    patient = await create_patient(auth_client)
    monkeypatch.setattr(
        ocr_batch_service,
        "call_ocr_service_stream",
        _fake_call_ocr_service_stream_by_filename(
            {
                "bead_specificity_page_1.jpg": {
                    "bead_specificity": [{"bead": "044", "antigen": "B76,Bw6", "mfi": 22362.49}]
                },
                "bead_specificity_page_2.jpg": {
                    "bead_specificity": [{"bead": "044", "antigen": "DQ4", "mfi": 179.54}]
                },
            }
        ),
    )

    start = await auth_client.post(
        "/ocr/extract-batch/jobs",
        files={
            "bead_specificity_page_1": FAKE_IMAGE,
            "bead_specificity_page_2": FAKE_IMAGE,
        },
        data={"patient_id": patient["id"]},
    )
    assert start.status_code == 202
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)
    assert body["status"] == "done"

    page_1_row = body["documents"]["bead_specificity_page_1"]["bead_specificity"][0]
    page_2_row = body["documents"]["bead_specificity_page_2"]["bead_specificity"][0]
    assert page_1_row["bead"] == "044"
    assert page_1_row["antigen"] == "B76,Bw6"
    assert page_1_row["panel"] == "class_i"
    assert page_2_row["bead"] == "044"
    assert page_2_row["antigen"] == "DQ4"
    assert page_2_row["panel"] == "class_ii"

    profiles_response = await auth_client.get(f"/patients/{patient['id']}/antibody-profiles")
    profiles = profiles_response.json()
    assert len(profiles) == 2

    by_panel = {p["panel"]: p for p in profiles}
    assert by_panel["class_i"]["bead_id"] == "044"
    assert by_panel["class_i"]["antigen"] == "B76,Bw6"
    assert by_panel["class_ii"]["bead_id"] == "044"
    assert by_panel["class_ii"]["antigen"] == "DQ4"


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
        # Captured from inside the extraction call itself -- this is the
        # only window in which the spool directory is actually observable
        # as still present. A plain `assert` in here would be swallowed by
        # stream_batch_extraction's own per-document try/except (it treats
        # any exception from call_ocr_service as a per-document error, not
        # something that propagates) rather than failing the test, so the
        # existence check is recorded here and asserted below instead,
        # where a failure actually fails the test.
        captured_spool_dir["path"] = upload.path.parent
        captured_spool_dir["existed_during_call"] = (
            upload.path.exists() and upload.path.parent.exists()
        )
        return HLA_TYPING_RESPONSE

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _fake)

    start = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    job_id = start.json()["job_id"]

    body = await _await_job_done(auth_client, job_id)

    assert body["status"] == "done"
    assert captured_spool_dir.get("existed_during_call") is True
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
