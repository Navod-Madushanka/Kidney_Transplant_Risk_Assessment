# app/tests/integration/test_ocr_job_db_sessions.py
"""Part H regression coverage.

app/services/ocr_job_service.py::run_extraction_job used to open a session
BEFORE the extraction loop and hold it open across the whole thing --
including every multi-minute await on ocr-service. `await db.commit()`
ends the transaction, not the connection checkout; that only happens when
the `async with` block exits. So a pooled connection sat checked out,
idle, for the full 1.5-3 minutes of each OCR call. At roughly 15
concurrent jobs (the old unconfigured default pool: 5 + 10 overflow),
every OTHER request -- logins, patient lookups, even the 2.5s polling
GETs -- queued behind pool_timeout and started failing, taking
/health/db (and with it an orchestrator's liveness probe) down along the
way. The reviewer that flagged the resulting symptom blamed the wrong
mechanism (BackgroundTasks don't touch a thread pool here -- run_
extraction_job is `async def`, and Starlette awaits async background tasks
directly on the event loop); the real defect was holding a DB connection
across a network call, and it would have survived a move to Celery/ARQ
unchanged, since the connection lifetime was set by the `async with`
scope, not by which process the coroutine ran in.

Fixing run_extraction_job's own session scoping wasn't the whole story,
either: FastAPI ties every `Depends(..., yield ...)` dependency's cleanup
(get_db included) to the outer, REQUEST-scoped AsyncExitStack, which only
closes AFTER `BackgroundTasks` finish running (confirmed against
fastapi/routing.py -- `request_response`'s `await response(...)`, which is
what actually runs queued background tasks, happens inside
`async with AsyncExitStack() as request_stack`, and get_db's cleanup is
registered on that same stack). So the request's own `db` session --
opened once via Depends(get_db) and shared by get_current_user and the
route handler -- stayed checked out for a BackgroundTasks job's entire
duration regardless of what run_extraction_job did internally. See
ocr_job_service.schedule_extraction_job's docstring for the fix
(asyncio.create_task instead of BackgroundTasks) -- these tests are what
stop either half of this regressing again.
"""
import asyncio

from httpx import AsyncClient

from app.db.session import engine
from app.services import ocr_batch_service
from app.tests.integration.test_ocr_jobs import FAKE_IMAGE, HLA_TYPING_RESPONSE, _await_job_done


async def test_no_pooled_connection_is_held_during_the_ocr_call(
    monkeypatch, auth_client: AsyncClient
):
    checked_out_during_call = []
    called = asyncio.Event()

    async def _fake(upload, document_type):
        # This is the assertion that matters: captured from INSIDE the
        # call that stream_batch_extraction awaits on ocr-service, at the
        # exact moment a held-open session would still be checked out.
        checked_out_during_call.append(engine.pool.checkedout())
        called.set()
        return HLA_TYPING_RESPONSE

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _fake)

    response = await auth_client.post(
        "/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE}
    )
    assert response.status_code == 202

    # The job is scheduled via asyncio.create_task (see
    # ocr_job_service.schedule_extraction_job), not FastAPI's
    # BackgroundTasks -- so this response can return before the job
    # coroutine has run at all. Wait for the OCR call to actually happen
    # before checking what it saw.
    await asyncio.wait_for(called.wait(), timeout=5.0)
    assert checked_out_during_call == [0]


async def test_polling_stays_responsive_under_concurrent_jobs(
    monkeypatch, auth_client: AsyncClient
):
    # Above pool_size + max_overflow (10 + 20 = 30, see app/db/session.py)
    # -- comfortably clears even the TUNED ceiling, not just the old
    # unconfigured one (5 + 10 = 15), so this stays a real regression
    # guard against someone re-wrapping the extraction loop in a session
    # even after the pool itself was widened.
    CONCURRENT_JOBS = 40
    release = asyncio.Event()

    async def _slow_fake(upload, document_type):
        await release.wait()
        return HLA_TYPING_RESPONSE

    monkeypatch.setattr(ocr_batch_service, "call_ocr_service", _slow_fake)

    # Jobs are scheduled via asyncio.create_task (not FastAPI
    # BackgroundTasks -- see schedule_extraction_job's docstring), so these
    # POSTs return as soon as each job's row is created, well before its
    # extraction call runs, rather than blocking on the (deliberately
    # never-released) fake above.
    responses = await asyncio.gather(
        *[
            auth_client.post("/ocr/extract-batch/jobs", files={"hla_typing_report": FAKE_IMAGE})
            for _ in range(CONCURRENT_JOBS)
        ]
    )
    assert all(r.status_code == 202 for r in responses)
    job_ids = [r.json()["job_id"] for r in responses]

    # Give every job's background task a chance to actually start --
    # either reach the OCR call, or (with ocr_max_concurrent_jobs=1) queue
    # behind app/services/ocr_job_service.py's extraction semaphore, which
    # -- correctly -- holds no DB session while queued.
    await asyncio.sleep(0.3)

    # pool_timeout is 10s (app/db/session.py) -- 5s here proves the GET
    # returns well inside that budget, not just eventually before it times
    # out. Regressing H3 (re-wrapping the extraction loop in a session)
    # would exhaust the pool at well under 40 concurrent holds and this
    # would time out instead.
    poll_response = await asyncio.wait_for(
        auth_client.get(f"/ocr/extract-batch/jobs/{job_ids[0]}"), timeout=5.0
    )
    assert poll_response.status_code == 200

    release.set()
    # Drain every job this test started before it ends, so none of them
    # are still running against a DB that the next test's cleanup is about
    # to truncate out from under them.
    await asyncio.gather(*(_await_job_done(auth_client, job_id) for job_id in job_ids))
