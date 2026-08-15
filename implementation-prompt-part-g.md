# Implementation prompt — Part G: Bounded memory for the extraction upload path

**Insert as Part G of `implementation-prompt.md`, after Part F. Everything below the line goes to your coding agent.**

---

## G0. The fact this is built on

`kidney-backend/app/api/ocr.py::_build_files_payload` reads every uploaded image fully into RAM before anything else happens:

```python
    for f in provided.values():
        _validate_file(f)          # content-type ONLY

    files_payload = {}
    for name, f in provided.items():
        contents = await f.read()  # full read into RAM
        files_payload[name] = (contents, f.filename, f.content_type)
```

and those bytes are then handed to a background task that outlives the request:

```python
    job = await create_extraction_job(db, current_doctor.id, files_payload, patient_id=patient_id)
    background_tasks.add_task(run_extraction_job, job.id, files_payload)
```

Three separate facts make this worse than it looks:

1. **There is no size limit anywhere in `kidney-backend` on this path.** `_validate_file` checks content-type only. One request with four large PNGs is unbounded resident memory. This does not need five concurrent users — it needs one.
2. **The bytes are held for the whole job, not the whole request.** A four-document job is HLA + crossmatch + two bead pages at 1.5–3 min each — five to eight minutes with every image pinned in the heap. Normal request memory frees in milliseconds; this does not.
3. **`ocr-service` checks size *after* reading.** `_authorize_and_read` does `contents = await file.read()` and *then* compares against `max_upload_size_mb`. The 10 MB cap cannot protect against a 500 MB upload, because the OOM happens before the check runs.

There is also a correction to make to the obvious mental model, because it changes what the fix has to be. **The JPEG bytes are not the largest allocation in this pipeline.** `ocr-service/app/extraction/preprocessing.py::orient_image` decodes to RGB via PIL: a 12-megapixel phone photo is roughly 36 MB resident as a bitmap regardless of the fact that the JPEG on the wire was 3 MB. Add `_b64()`'s ~1.33× copy and, for bead specificity, eight tiles on top. Peak memory lives in `ocr-service`, during processing — not in `kidney-backend`, while queued.

So this part does two things that are often conflated:

- **Spooling to disk** fixes the *unbounded* and *held-too-long* problems in `kidney-backend`.
- **A concurrency gate** fixes the *peak* problem in `ocr-service`. Spooling alone does not touch it, because N concurrent jobs still means N concurrent PIL decodes.

Both are needed. Neither is large.

---

## G1. Scope, and the storage decision

**Chosen approach: spool to local disk in `kidney-backend`, stream from disk to `ocr-service` over the existing HTTP multipart call.**

Object storage was considered and rejected **for now**:

| Option | Verdict |
|---|---|
| Local temp dir | **Chosen.** Backend is one uvicorn process on one host; disk is already how `report_file_service.py` persists uploads. Zero new infrastructure. |
| S3 / MinIO | Rejected. Nothing in the stack uses object storage today (no S3, MinIO, or Azure Blob anywhere). It buys correctness only once the backend is multi-worker or multi-host — which it is not. |
| Redis / Celery / arq queue | Rejected. `redis_url` exists in `Settings` but is explicitly commented as not read anywhere. Introducing a broker is a much larger change than the problem justifies, and `BackgroundTasks` is not the thing failing here. |

**The trigger for revisiting this is a single line: the day `uvicorn` gets `--workers`, or the backend runs on more than one host, local-disk spooling and the in-process semaphore in G8 both become wrong.** Write that down in the code comment, not just here.

The house pattern already exists — reuse it rather than inventing one. `app/services/report_file_service.py::_save_upload` does exactly this:

```python
    size = 0
    try:
        with absolute_path.open("wb") as out:
            while chunk := await file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > max_size_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE, ...
                    )
                out.write(chunk)
    except HTTPException:
        absolute_path.unlink(missing_ok=True)
        raise
```

Server-generated `uuid4().hex` filenames, extension from the validated content-type, never the client filename, `unlink(missing_ok=True)` on failure. Match it.

The four steps below are **independently shippable in this order**. G4 alone removes the unbounded-upload risk; do not hold it behind the rest.

---

## G2. Settings

`kidney-backend/app/core/config.py::Settings`:

| Setting | Default | Notes |
|---|---|---|
| `ocr_spool_dir` | `"uploads/ocr_spool"` | Deliberately **not** `report_files_storage_dir`. That directory holds permanent clinical attachments; this one is ephemeral and gets swept. Never mix the two lifecycles in one tree. |
| `ocr_upload_max_size_mb` | `15` | See the sync-warning below. |
| `ocr_spool_max_age_hours` | `6.0` | Sweep cutoff. Must comfortably exceed the longest plausible job (~10 min). |
| `ocr_max_concurrent_jobs` | `1` | G8. |

`ocr-service/app/core/config.py::Settings` already has `max_upload_size_mb: int = 10`.

**These two caps must stay equal.** If `kidney-backend` accepts 15 MB and `ocr-service` rejects above 10 MB, the upload succeeds, the job starts, and then dies mid-extraction with a 413 the doctor cannot act on. Raise `ocr-service`'s `max_upload_size_mb` to `15` in the same change and add a comment on both pointing at the other. 15 MB is chosen over 10 because a 300 dpi A4 scan of a bead-specificity chart is legitimately 3–6 MB and a rejected real report is a clinical workflow failure, not a nuisance.

---

## G3. New module: `app/services/ocr_spool_service.py`

Intended signatures only:

```python
@dataclass(frozen=True)
class SpooledUpload:
    path: Path
    filename: str        # server-generated, e.g. "hla_typing_report.jpg"
    content_type: str


async def spool_uploads(slots: dict[str, UploadFile]) -> tuple[Path, dict[str, SpooledUpload]]:
    """Stream each upload to <ocr_spool_dir>/<uuid4hex>/ and return
    (spool_dir, {slot: SpooledUpload}). Raises 413 mid-stream; removes the
    whole spool_dir before re-raising so no partial write survives."""


def discard_spool(spool_dir: Path) -> None:
    """shutil.rmtree(spool_dir, ignore_errors=True). Never raises."""


def sweep_stale_spools(max_age_hours: float) -> int:
    """Remove spool dirs whose mtime is older than the cutoff. Returns count."""
```

Details that matter:

- **One directory per job**, named `uuid4().hex`. Cleanup is then a single `rmtree` — no per-file bookkeeping, no partial-cleanup states.
- **Cap during the stream, not after.** Same running-total pattern as `_save_upload`. A 500 MB upload must be rejected after ~16 MB is written, never buffered.
- Starlette's `UploadFile` is already a `SpooledTemporaryFile` that rolls to disk above 1 MiB — `await file.read()` with no argument is what forces it into RAM. Prefer `shutil.copyfileobj`-style chunked copying, and check `file.size` first (populated by Starlette's multipart parser; FastAPI ≥0.115 is new enough) as a cheap pre-check before writing anything. Keep the running cap anyway: `file.size` can be `None`.
- **Filenames are server-generated** from the validated content-type (`image/jpeg` → `.jpg`, `image/png` → `.png`), named after the slot. The client filename is never used for anything, so path traversal is impossible by construction.
- `discard_spool` must never raise. A cleanup failure is a log line, never a job failure. See G12.

---

## G4. `app/api/ocr.py`

Replace the read-into-RAM in `_build_files_payload` with a call to `spool_uploads`. Return type becomes `dict[str, SpooledUpload]`.

**Preserve the slot insertion order.** The existing comment on `slots` is load-bearing — insertion order *is* dispatch order (HLA → crossmatch → bead 1 → bead 2), chosen so the fastest and most clinically valuable fields reach the doctor first. Do not reorder while refactoring.

Validation order in `start_extract_batch_job` stays as-is: at-least-one-file → content-type → patient ownership → *then* spool → then create the job row. The docstring's promise that "all upfront validation happens before the job row is even created" must remain true, and 413 now joins that set.

Two new failure paths to handle:

```python
    spool_dir, files = await _build_files_payload(...)
    try:
        job = await create_extraction_job(db, current_doctor.id, list(files), patient_id=patient_id)
    except Exception:
        discard_spool(spool_dir)
        raise
    background_tasks.add_task(run_extraction_job, job.id, spool_dir, files)
```

`create_extraction_job` currently takes `files` only to call `_initial_documents(list(files.keys()))` — it never touches the bytes. Change its signature to `slot_names: Sequence[str]` so it stops pretending to care.

**The other two endpoints on this module read into RAM the same way and both need the same treatment**, wrapped in `try/finally: discard_spool(...)` since they are synchronous:

- `POST /ocr/extract-batch` — holds bytes for the *entire* multi-minute extraction, same as the job path. Same problem, no job row.
- `POST /ocr/lab-report` — `contents = await file.read()`, single image, shorter hold, but still uncapped.

If `/ocr/extract-batch` turns out to have no remaining callers now that the frontend uses the jobs endpoint, deleting it is a better fix than porting it. Check before you port.

---

## G5. `app/services/ocr_job_service.py`

```python
async def run_extraction_job(
    job_id: uuid.UUID, spool_dir: Path, files: dict[str, SpooledUpload]
) -> None:
```

Wrap the entire existing body in `try/finally`, with `discard_spool(spool_dir)` in the `finally`. This must run on the success path, the per-document-failure path, and the job-level exception path alike — the existing outer try/except that sets `status=FAILED` and `job.error` sits *inside* this, not around it.

Keep `async_session_maker` as-is. The docstring's reasoning ("it owns its own DB session rather than reusing the request-scoped one, which is closed by then") is still correct and unaffected.

---

## G6. `ocr_batch_service.py` and `ocr_client.py`

`stream_batch_extraction` / `run_batch_extraction` take `dict[str, SpooledUpload]`. The sequential loop stays sequential — the "one image at a time" comment is a real constraint, not a leftover.

`ocr_client.call_ocr_service` and `call_ocr_service_stream` change from `(file_bytes, filename, content_type, document_type)` to `(upload: SpooledUpload, document_type: str)` and pass an **open file handle** to httpx, which streams it instead of buffering:

```python
    with upload.path.open("rb") as fh:
        response = await client.post(
            f"{settings.ocr_service_url}/extract",
            headers={"X-Internal-API-Key": settings.ocr_service_api_key},
            data={"document_type": document_type},
            files={"file": (upload.filename, fh, upload.content_type)},
        )
```

Two things that will bite you if you skip them:

- **For `call_ocr_service_stream`, the file handle must stay open for the entire streamed response.** The request body is consumed lazily, so `with upload.path.open("rb")` has to wrap the whole `async with client.stream(...)` block, not just the call that creates it. Closing it early gives you a truncated or empty multipart body with no obvious error.
- **If a retry is ever added here, re-open or `seek(0)` first.** There is no retry today; a retry on a consumed handle silently uploads zero bytes.

Passing a sync file object to an async client means httpx reads it in chunks on the event loop. Off local disk at 1 MiB chunks this is immaterial; if it ever shows up in a profile, `anyio.open_file` is the escape hatch. Do not pre-emptively async it.

---

## G7. `ocr-service`: cap before read, not after

`app/api/routes.py::_authorize_and_read` currently does `contents = await file.read()` then `if len(contents) > max_bytes: 413`. Invert it: check `file.size` when present, and read in chunks with a running cap otherwise. Same pattern as G3.

This is the single most exploitable spot in the pipeline, because the 413 that is supposed to protect the service only fires once the damage is done.

Leave `orient_image`'s full decode alone. The comment about the reverted downscale is a real incident — **do not reintroduce resizing**, it caused a misread of clinical data. Peak decode memory is addressed by bounding concurrency in G8, not by touching image quality.

---

## G8. Concurrency gate

Add a module-level `asyncio.Semaphore(settings.ocr_max_concurrent_jobs)` in `ocr_job_service.py`, acquired around the extraction loop inside `run_extraction_job` — after the job row is loaded, so the job still exists and still returns 202 instantly, it just waits its turn. Its documents stay `pending`, which the existing `ExtractionProgressList.jsx` already renders correctly, so no frontend change is required.

**Default 1.** Ollama serializes inference regardless, so raising this does not increase throughput — it only multiplies concurrent PIL decodes in `ocr-service`. That is the exact allocation this part exists to bound.

One consequence to accept deliberately: with N=1, a stuck job blocks the queue for up to `ocr_service_timeout_seconds`, currently `1200.0`. Twenty minutes is roughly 6× the worst legitimate bead page. **Review that number in this change** — 600 s keeps ample headroom while halving the worst-case head-of-line block. If you would rather not touch it, N=2 is the alternative; do not go higher.

---

## G9. Startup reconciliation

In the `app/main.py` lifespan handler, on boot:

1. `sweep_stale_spools(settings.ocr_spool_max_age_hours)` — catches spool dirs orphaned by a hard crash, which the `try/finally` in G5 cannot cover.
2. **Mark every `OcrExtractionJob` still in `RUNNING` as `FAILED`**, with `error` set to something like `"Server restarted during extraction. Please re-upload and try again."`

Item 2 is a pre-existing bug this change makes it natural to fix: `BackgroundTasks` die with the process, so a job left `RUNNING` at boot is definitionally dead, and today it sits there forever while the frontend polls it every 2.5 s indefinitely. On a single-worker deployment this inference is always safe. **It stops being safe the moment there is more than one worker** — same comment as G1.

Startup-only sweeping is sufficient because `try/finally` handles the normal path and the process restarts on every deploy. A periodic sweeper is not worth an `asyncio` task here; say so in the comment so nobody adds one later thinking it was an oversight.

---

## G10. Existing data

**No Alembic migration is required.** Nothing in this part changes a table. `OcrExtractionJob` keeps its current columns — spool location lives in the background-task argument, not the database, because jobs are not resumable today and storing the path would buy nothing but an information-disclosure risk in `OcrJobStatusResponse.documents`, which is returned to the client.

If job resumption is ever added, that is the moment to add a `spool_dir` column — and to make sure it is stripped from the response schema.

One operational note: `ocr_extraction_jobs` rows accumulate forever with no TTL anywhere in the codebase. That is out of scope here, but it is the natural next follow-up and belongs on the backlog rather than in this part.

---

## G11. Tests

**Backend**

- `app/tests/unit/test_ocr_spool_service.py` (new) — one file written per provided slot under a fresh directory; on-disk filename is server-generated from content-type and never the client filename; oversize upload raises 413 **and leaves no partial file or directory**; `discard_spool` removes the tree and does not raise on a missing path; `sweep_stale_spools` removes an artificially back-dated directory and leaves a fresh one.
- `app/tests/unit/test_ocr_batch_service.py` (fixtures rewritten) — `FAKE_FILE = (b"...", "file.jpg", "image/jpeg")` becomes a `SpooledUpload` pointing at a `tmp_path` file, and the monkeypatched fakes for `ocr_batch_service.call_ocr_service` / `call_ocr_service_stream` take `(upload, document_type)`. **All ~15 existing assertions must pass unchanged** — this is a signature refactor, not a behaviour change. If one of them needs its expectation edited, stop and work out why.
- `app/tests/integration/test_ocr_jobs.py` (extended) — every current assertion still passes (202 + job_id, 400 with no file, done + hydrated documents, per-document failure does not fail the job, bead progress reaches total, cross-doctor 404, `patient_id` auto-save of unverified antibody profiles, 401). The monkeypatch seams at `ocr_batch_service.call_ocr_service*` stay where they are, and the suite keeps relying on Starlette running `BackgroundTasks` inline. Add: spool directory exists while the job runs and is gone after `_await_job_done`; a job that fails still cleans its spool; an oversize upload returns 413 **with no job row created**.
- `app/tests/unit/test_ocr_client.py` (new) — the multipart body is built from an open file handle, not a `bytes` object. This is the test that stops a future refactor from quietly reintroducing `path.read_bytes()`.
- Startup reconciliation — a `RUNNING` job row present at lifespan start comes out `FAILED` with the restart message; a `DONE` row is untouched.

**ocr-service**

- An upload above `max_upload_size_mb` returns 413 without the full body being buffered (assert on the cap firing mid-stream, not just on the status code).

**Frontend**

- `src/api/ocr.js` / `PhotoUploadsStep.jsx` — a 413 from `POST /ocr/extract-batch/jobs` renders a specific message naming the limit ("This image is larger than the 15 MB limit"), not the generic extraction-failed path. A doctor who photographed a chart at full resolution needs to know to retake it, not that "something went wrong."

`ruff check .` and `uv run pytest -v` must both be green; CI runs them in that order against `postgres:16`.

---

## G12. Do not

- **Do not add `--workers` to uvicorn** while the semaphore in G8 and the startup reconciliation in G9 exist. Both silently become wrong with a second process — the gate stops gating and live jobs get marked failed on every restart of any worker.
- **Do not introduce Celery, RQ, arq, or Redis** as part of this. `BackgroundTasks` is not the thing failing; unbounded reads are.
- **Do not add S3 or MinIO.** Single host, single process — local disk is the correct answer until that changes.
- **Do not put spool paths in `OcrJobStatusResponse`.** Server filesystem layout is not the client's business.
- **Do not derive on-disk filenames from `file.filename`.** `report_file_service.py` already documents why; the same reasoning applies verbatim.
- **Do not raise `ocr_max_concurrent_jobs` to speed things up.** Ollama serializes anyway, so the only thing extra concurrency buys is more simultaneous PIL decodes — the exact allocation this part bounds.
- **Do not let a cleanup failure fail a successful job.** `discard_spool` logs and returns; extracted clinical data is never discarded because a directory would not delete.
- **Do not drop the `try/finally` in G5 in favour of relying on the sweep.** The sweep is the crash backstop, not the mechanism.
- **Do not reintroduce image downscaling in `ocr-service`** as a memory optimisation. It was tried, it caused a real misread, and it was reverted for that reason.
