# Implementation prompt — Part H: The extraction job's real saturation bug

**Insert as Part H of `implementation-prompt.md`, after Part G. Everything below the line goes to your coding agent.**

---

## H0. The reviewer's mechanism is wrong. The symptom is real.

The claim under review: *"BackgroundTasks run inside the same event loop or worker process as your API. 8 tiles through Ollama takes 1.5–3 min/page. Under load your process pool saturates and the backend becomes unresponsive to polling GETs. Fix: Celery/ARQ/Temporal + Redis."*

The predicted symptom — `GET /ocr/extract-batch/jobs/{id}` stalls under load — is real and reachable. The stated cause is not. Three checks kill it:

| Claim | Reality in this codebase |
|---|---|
| Background work saturates the process/thread pool | `run_extraction_job` is `async def`. Starlette `await`s coroutine background tasks directly on the event loop; only **sync** `def` tasks go to the AnyIO threadpool. That pool is untouched. |
| CPU-bound tile processing blocks the API | Grep of `ocr_job_service.py`, `ocr_batch_service.py`, `ocr_client.py`: no PIL, no base64, no numpy. **All** decode/tiling/encode lives in `ocr-service`. The backend's per-job CPU is a `dict()` copy, an `asdict()`, and a `json.loads()` of `{"type":"progress","completed":N,"total":8}`. |
| The API can't serve polling requests during a job | Every path operation in `app/api/` is `async def`. During a job the backend does nothing but `await` an httpx socket, which yields the loop. Polling is served fine. |

An idle coroutine parked on `await client.post(...)` for three minutes costs a few KB. That is not the problem.

**The problem is one line of scoping.** `app/services/ocr_job_service.py`:

```python
async def run_extraction_job(job_id: uuid.UUID, files: ...) -> None:
    async with async_session_maker() as db:          # <-- opens here
        job = await db.get(OcrExtractionJob, job_id)
        ...
            async for event in stream_batch_extraction(files):   # <-- 5-8 minutes
                ...
                job.documents = documents
                await db.commit()
```

The session wraps the entire `async for`. `await db.commit()` ends the *transaction*; it does **not** return the connection to the pool — SQLAlchemy releases on `close()`, which happens when the `async with` exits. So a pooled asyncpg connection is checked out for the full five-to-eight minutes, **idle for more than 99% of it**, waiting on an HTTP call to another service.

And the pool is untuned. `app/db/session.py` in full:

```python
engine = create_async_engine(settings.database_url, echo=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
```

No `pool_size`, no `max_overflow`, no `pool_timeout`, no `pool_pre_ping`. Defaults apply: **5 + 10 overflow = 15 connections, 30 s timeout.**

---

## H1. The failure cascade

At roughly 15 concurrent extraction jobs, every connection in the pool is checked out by a coroutine that is doing nothing:

1. Job 16, and **every** other request — login, patient list, the 2.5 s polling GETs — waits on `pool_timeout`.
2. After 30 s they raise `TimeoutError`. The backend is now effectively down while its CPU sits idle.
3. `useExtractionJobPolling.js` uses `POLL_INTERVAL_MS = 2500` with **no backoff and no failure counter** — a failed poll is swallowed and retried on the next tick, forever. Every client hammers the dying backend at a fixed 2.5 s, amplifying the pressure instead of relieving it.
4. `/health/db` depends on `get_db`, so **the liveness probe hangs too**. An orchestrator reads the backend as down and restarts it.
5. The restart kills every in-flight `BackgroundTask`. With no lifespan hook and no reconciliation, those rows are stranded at `status=RUNNING` forever, and their clients poll them forever.

Pool exhaustion turns into a restart loop that destroys exactly the work it was trying to protect. That is the finding worth acting on — not the threadpool.

---

## H2. Why Celery would not have fixed this

This matters more than the fix itself, because adopting the reviewer's remedy would have cost a week and left the bug in place.

**Move `run_extraction_job` verbatim into a Celery or ARQ worker and it still holds a DB connection for eight minutes.** The connection lifetime is set by the `async with async_session_maker()` scope, not by which process the coroutine runs in. A worker pool of 8 with the current code exhausts the same 15-connection pool at the same rate — and now from a process that has no visibility into the API's pool at all.

A distributed queue fixes *durability* and *horizontal scale*. It does not fix *holding a database connection across a network call*. Those are unrelated defects that happen to produce the same stall.

There is also no throughput argument here. `docker-compose.yml` pins `OLLAMA_NUM_PARALLEL=1` and `OLLAMA_MAX_LOADED_MODELS=1`, and prod is CPU-only by design (GPU appears only in `docker-compose.override.yml`). **The system does exactly one inference at a time and no queue changes that.** Ten Celery workers would produce ten processes taking turns at the same single-threaded Ollama.

---

## H3. Fix 1 — scope the session to the write, not the job

**The rule, and the only thing to remember from this part: never hold an `AsyncSession` across an `await` on `ocr-service`.**

Restructure `run_extraction_job` so a session is opened per write and closed immediately:

```python
async def run_extraction_job(job_id, spool_dir, files) -> None:
    try:
        async with async_session_maker() as db:          # existence check only
            if await db.get(OcrExtractionJob, job_id) is None:
                return

        async for event in stream_batch_extraction(files):   # NO session held here
            async with async_session_maker() as db:
                job = await db.get(OcrExtractionJob, job_id)
                if job is None:
                    return
                job.documents = _apply_event(job.documents, event)
                await db.commit()

        async with async_session_maker() as db:           # finalise
            job = await db.get(OcrExtractionJob, job_id)
            if job.patient_id is not None:
                await _save_bead_specificity_if_present(db, job)
            job.status = OcrExtractionJobStatus.DONE
            await db.commit()

    except Exception as exc:
        async with async_session_maker() as db:           # fresh session, not a rollback
            job = await db.get(OcrExtractionJob, job_id)
            if job is not None:
                job.status = OcrExtractionJobStatus.FAILED
                job.error = str(exc)
                await db.commit()
    finally:
        discard_spool(spool_dir)                          # from Part G
```

Details that will bite:

- **Re-fetch `job` in every session.** `expire_on_commit=False` keeps attributes readable after commit, but the instance is still bound to a closed session — reusing it across sessions raises or silently no-ops. Extract the event-application logic into a pure helper (`_apply_event(documents, event) -> dict`) so this stays readable.
- **The error path opens a fresh session** rather than calling `rollback()` on a possibly-broken one. If the failure *was* a pool timeout, the old session is unusable.
- **Read-modify-write of `documents` is now split across transactions.** Safe today: exactly one background task writes a given job. If that ever stops being true, this needs `SELECT ... FOR UPDATE`. Put that in the comment.
- **Yes, this is more round-trips** — a `SELECT` plus an `UPDATE` per event instead of one `UPDATE`. That is a few milliseconds against minutes of inference, and it trades a rounding error of latency for the difference between 15 concurrent jobs and effectively unlimited ones. Do not "optimise" it back.

---

## H4. Fix 1b — configure the engine

`app/db/session.py`:

| Setting | Value | Why |
|---|---|---|
| `echo` | `settings.sql_echo`, default **`False`** | Currently `True` **unconditionally**. Every statement is logged including the full `documents` JSONB blob on every commit — and that blob grows with each bead row, on 16+ commits per job. This is filling disk and slowing every write in production for no benefit. |
| `pool_size` | 10 | Modest bump once connections are short-lived. |
| `max_overflow` | 20 | |
| `pool_timeout` | **10**, not the 30 s default | Fail fast. A 30 s stall on every request under pressure is worse than a quick 503 the frontend can show. |
| `pool_pre_ping` | `True` | asyncpg connections get killed by the DB or the network; without this a stale one surfaces as a random mid-job error. |

Add `await engine.dispose()` to the lifespan shutdown introduced in Part G's G9.

**Raising `pool_size` is not an alternative to H3.** It raises the ceiling on a leak of connection-*time*; the ratio of held-to-useful stays at 99:1 and the wall just moves.

---

## H5. Ordering: this must land with or before Part G's G8

Part G adds `asyncio.Semaphore(ocr_max_concurrent_jobs=1)` around the extraction loop. **Applied to the current session structure, that semaphore makes this bug worse, not better.**

With the session opened first and the semaphore acquired second, jobs 2..N sit blocked on the semaphore *while each holds a pooled connection*. What is today a transient squeeze under real concurrency becomes a guaranteed stall at 15 queued jobs, and the queue wait is unbounded rather than bounded by extraction time.

**Either land H3 first, or land them together with the semaphore acquired outside any session scope.** Do not ship G8 alone. Update Part G's G8 with a pointer to this section.

---

## H6. Fix 2 — `ocr-service` blocks its own event loop

The reviewer's mechanism is wrong about the backend but roughly right about the *other* service, which nobody reviewed:

- `orient_image()` (PIL decode + EXIF transpose) and `make_row_band_tiles()` (8 crops + 8 PNG encodes) are called **synchronously inside `async def` handlers**, with no `run_in_executor`. They block ocr-service's event loop outright — during a decode it cannot accept a new request or answer a health check.
- The only `asyncio.Semaphore` is created **inside** `extract_bead_specificity_stream`, so `CONCURRENT_TILE_LIMIT=1` is per-request. Three concurrent jobs get three independent semaphores of one = three tiles in flight. The comment in `llm_extract.py` documents exactly this hazard for tiles within a request; it recurs unfixed across requests.
- `OLLAMA_MAX_QUEUE` is **unset**, so it defaults to 512. Overflow requests do not fail fast — they queue, and each queued tile burns its own 180 s `REQUEST_TIMEOUT_SECONDS` *while waiting*, producing cascading timeouts that look like model failures.

Three changes:

1. Wrap the PIL calls: `await asyncio.to_thread(orient_image, ...)` and the same for `make_row_band_tiles`. The loop stays responsive; health checks answer during a decode.
2. **Module-level** `asyncio.Semaphore(1)` in `app/api/routes.py`, acquired by both `/extract` and `/extract/stream`. This is the authoritative concurrency bound because it sits closest to the resource. Part G's backend-side semaphore stays as well — they are cheap, and the backend is not the only possible caller.
3. Set `OLLAMA_MAX_QUEUE=8` in compose (roughly one page of tiles). With the semaphore in place the queue should never exceed 1; this is the backstop for when someone removes it.

---

## H7. Fix 3 — `--reload` is in the production image

`ocr-service/Dockerfile`:

```
CMD ["uv","run","uvicorn","app.main:app","--host","0.0.0.0","--port","8001","--reload"]
```

combined with `volumes: [./app:/app/app]` in the base `docker-compose.yml`. **Touching any file under `./app` on the host restarts the worker and destroys every in-flight multi-minute extraction.** The backend's own Dockerfile has no `--reload`; this is an oversight in one image, not a convention.

Move `--reload` and the bind mount into `docker-compose.override.yml` alongside the GPU reservation, where the other dev-only settings already live.

While in compose: neither service has `mem_limit` or a `deploy.resources` cap. Given Part G established that peak memory lives in ocr-service's PIL decodes, put a limit on ocr-service so it OOMs its own container instead of the host.

---

## H8. Fix 4 — polling must back off

`useExtractionJobPolling.js` keeps a fixed 2.5 s cadence through failures forever, which is what turns a squeeze into a stampede (H1, step 3).

- Keep 2.5 s for **successful** polls — that cadence is the progress UX and is worth the requests.
- On failure, back off exponentially: 2.5 → 5 → 10 → 20, cap 30 s. Reset to 2.5 s on the first success.
- Track consecutive failures. After ~4, surface "Lost contact with the server — still trying" rather than a silent frozen progress bar. The job is very likely still running server-side; say so, because the doctor's instinct will otherwise be to re-upload and start a second five-minute job.
- `BackgroundJobsProvider.startJob` has no dedup guard, so a double-click on `NewPairPage` registers the same `jobId` twice and polls it at 2×. Guard on `jobId` already being tracked.

---

## H9. The queue decision

**Verdict: do not adopt a distributed task queue in this change. Fix H3 and H6; revisit under the trigger below.**

| Option | Verdict |
|---|---|
| **Celery** | **Reject.** Sync-first prefork design in an all-async codebase — it would need either a sync httpx client or an event loop nested in each worker. Heavy operational surface. And per H2, it does not fix the actual bug. |
| **Temporal** | **Reject.** Requires running a Temporal cluster for a single-host deployment doing one inference at a time. The durability guarantees are real and enormously out of proportion here. |
| **ARQ** | **Defer, with a trigger.** The right choice *if* the trigger fires: async-native, small, Redis-backed, and `redis_url` already exists in `Settings`. |
| **Status quo + H3/H6** | **Adopt now.** Removes the saturation, bounds concurrency, keeps the stack at Postgres + FastAPI + Ollama. |

**The trigger to revisit — write this in the code comment, not just here.** Adopt ARQ when either becomes true:

1. Losing an in-flight extraction to a backend restart is no longer acceptable. This is the real remaining gap: `BackgroundTasks` die with the process, there is **no retry anywhere** in the job path and no `attempts` column, so a deploy at the wrong moment costs a doctor five to eight minutes with no recovery. Part G's startup reconciliation makes that *visible* (the job goes `FAILED` instead of stranded `RUNNING`) but does not make it *survivable*.
2. The backend needs more than one process — at which point Part G's semaphore, Part G's startup reconciliation, and local-disk spooling all break together.

Neither is true today. Both are plausible within a year.

---

## H10. If the trigger fires: the ARQ shape

Sketch only — **do not build this now.**

- `arq` dependency; `redis` service in compose; a `worker` container running `arq app.worker.WorkerSettings` off the same image.
- `run_extraction_job` becomes an ARQ task taking `(job_id, spool_dir, slot_descriptors)`. The body is unchanged if H3 has landed — that is the point of doing H3 first.
- `WorkerSettings.max_jobs = 1` replaces both semaphores. `job_timeout` slightly above `ocr_service_timeout_seconds`.
- ARQ's built-in retry with `max_tries=2` covers transient ocr-service failures. Add an `attempts` column to `ocr_extraction_jobs` so the UI can say "retrying (2 of 2)".
- **Spooling must move off local disk in the same change** — a separate worker container cannot read the API container's `uploads/ocr_spool`. Either a shared named volume (single host) or object storage (multi-host). This is the Part G G1 trigger firing at the same moment; the two are the same decision.

---

## H11. Tests

**Backend**

- `app/tests/integration/test_ocr_job_db_sessions.py` (new) — **the regression test that matters.** Monkeypatch `ocr_batch_service.call_ocr_service` with a fake that records `engine.pool.checkedout()` at the moment it is called, then returns a canned result. Run a job and assert the recorded value is **0**: no pooled connection may be held while the OCR call is in flight. This is the test that stops someone re-wrapping the loop in a session six months from now.
- Same file — start N concurrent jobs against a fake OCR client that sleeps, and assert `GET /ocr/extract-batch/jobs/{id}` still returns 200 well inside `pool_timeout` while they run. Choose N above the old ceiling of 15 so the test would have failed before H3.
- `app/tests/integration/test_ocr_jobs.py` — every existing assertion must pass unchanged (202 + job_id, 400 with no file, done + hydrated documents, per-document failure does not fail the job, bead progress reaches total, cross-doctor 404, `patient_id` auto-save, 401). This is a scoping refactor; behaviour is identical.
- Add to it: a job whose OCR call raises still ends `FAILED` with `error` set **and** its spool discarded — proving the fresh-session error path works when the original session is gone.
- `app/tests/unit/test_db_session_config.py` (new) — assert `echo` is `False` by default and `pool_pre_ping` is on. Cheap, and `echo=True` has already escaped into production once.

**ocr-service**

- A `GET /health` returns promptly while an `/extract` request is mid-PIL-decode — proves the `to_thread` offload. Without it this test hangs, which is the correct failure.
- Two concurrent `/extract` requests serialise rather than decoding in parallel — proves the module-level semaphore.

**Frontend**

- Poll failures back off (2.5 → 5 → 10 → 20, capped) and reset to 2.5 s on the next success.
- After ~4 consecutive failures the "lost contact, still trying" message renders and the job is **not** marked failed client-side.
- `startJob` called twice with the same `jobId` registers one poller.

`ruff check .` then `uv run pytest -v` must be green.

---

## H12. Do not

- **Do not adopt Celery, RQ, or Temporal for this.** Per H2, none of them fix a connection held across an `await`, and Ollama at `OLLAMA_NUM_PARALLEL=1` gives them nothing to parallelise.
- **Do not add ARQ "while we're in here."** It is gated on H9's trigger, and it is strictly easier after H3 lands.
- **Do not hold an `AsyncSession` across an `await` on `ocr-service`.** If you remember one line from this part, this is it.
- **Do not treat a larger `pool_size` as the fix.** It moves the wall; the 99:1 idle ratio is unchanged.
- **Do not ship G8's semaphore before or without H3.** It converts a squeeze into a guaranteed stall — see H5.
- **Do not leave `echo=True`.** It logs the whole `documents` JSONB on every one of 16+ commits per job.
- **Do not ship `--reload` in a production image.** A stray file touch destroys in-flight clinical extractions.
- **Do not remove Part G's backend-side semaphore** in favour of ocr-service's. Defence in depth on the resource that OOMs is worth two cheap semaphores.
- **Do not "optimise away" the per-event `SELECT`** introduced in H3. It is milliseconds against minutes, and it is the whole point.
