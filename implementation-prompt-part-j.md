# Implementation prompt — Part J: Deleting the unattended write, and a verdict on the five proposed enhancements

**Insert as Part J of `implementation-prompt.md`, after Part I. Everything below the line goes to your coding agent.**

---

## J0. Confirmed — but the staging layer the reviewer asks for already exists

The finding: *auto-saving unverified OCR results directly to `antibody_profiles` at registration pollutes the primary database with dirty draft state. Fix: hold results in a staging/draft JSON column on the job record or a dedicated `DraftRegistration` table.*

The direction is right. The build is not needed. **`OcrExtractionJob.documents` is already that JSON column.** `run_extraction_job` writes the entire `DocumentChunk` into it — not just progress:

```python
elif isinstance(event, DocumentChunk):
    chunk_data = asdict(event)          # patient_details, donor_details, patient_hla,
    chunk_data.pop("document_type")     # donor_hla, bead_specificity, errors
    documents[event.document_type] = {
        "status": "done", "completed": total, "total": total, **chunk_data,
    }
```

`OcrJobDocumentStatus` types it back out as `bead_specificity: list[BeadSpecificityEntryOcr]`. The frontend already polls it. The compatibility wizard already consumes it end-to-end with **zero writes to core tables** — that path is the proof that the auto-save is unnecessary, not a missing feature.

A `DraftRegistration` table would be a second copy of data that is already staged, already polled, and already correct.

**The fix is a deletion.** `_save_bead_specificity_if_present` and its call site.

---

## J1. The severity is not pollution. It is destruction, and a silent denial of service.

Two corrections to the stated harm, in opposite directions.

**Downward: unverified rows cannot reach a clinical calculation today.** The protection is a gate rather than a filter, but it holds. `compatibility_precondition_service.unverified_data_gaps` includes `("patient_antibody_profile_unverified", …, "antibody_profile_verified")`, and `POST /compatibility/check` refuses to call `run_match_pipeline` while it is False. `load_exchange_pool` filters `Patient.antibody_profile_verified.is_(True)` in its WHERE clause. So cPRA, DSA and exchange matching never see unverified rows. "Dirty data drives a decision" is not the risk.

**Upward, and this is the actual bug: the write is a hard DELETE with no guard, and it can destroy human-verified clinical data.**

```python
await db.execute(delete(AntibodyProfile).where(AntibodyProfile.patient_id == patient_id))
for entry in entries:
    db.add(AntibodyProfile(patient_id=patient_id, antigen=entry.antigen, mfi=entry.mfi))
```

The only upstream check is ownership — `get_patient_by_id_for_doctor` → 404. **There is no check on `antibody_profile_verified`, no check for existing rows, no merge, no soft delete, no history table.** So:

1. A doctor who owns a patient with a fully verified, hand-checked ~100-row antibody profile POSTs `/ocr/extract-batch/jobs` with that `patient_id` and a bead page.
2. Minutes later, from a background task, after the browser has usually navigated away, the verified rows are **hard-deleted** and replaced with unverified model output — output that, per Part I, may contain duplicates and dropped rows.
3. `new_verified = previous_verified if ocr_verified is None else ocr_verified` with `ocr_verified=False` takes the `else` branch, so the flag correctly flips True → False. That is the one thing working as designed — and it is what converts the incident into a **silent denial of service**: the patient immediately drops out of the exchange pool, and every compatibility check for them hard-fails until a human re-transcribes ~100 rows by hand from the paper chart.

There is no undo. `antibody_profiles` has no history, no `deleted_at`, and the audit log records only `entry_count`.

---

## J2. Part F already forbids the path that creates this

`implementation-prompt-part-f.md`, §F12:

> **Do not extract the bead chart during registration.** It is minutes per page, the values are not needed to create a record.

That decision, already written and already agreed, removes the auto-save path entirely — `patient_id` is only ever passed by `NewPairPage.jsx`'s registration-time bead extraction. **Finding A is a Part F item that has not been implemented yet, not a new architectural question.** Implement F12 and this closes on its own.

Treat the rest of this section as defence in depth for the case where registration-time extraction survives in some form.

---

## J3. Fix 1 — delete the unattended write

- Delete `_save_bead_specificity_if_present` and its call in `run_extraction_job`.
- Keep `patient_id` on `OcrExtractionJob`. It is still useful for scoping and audit; it just stops authorising a write.
- Per F12, remove the bead-specificity slots from `NewPairPage.jsx` so registration no longer starts multi-minute extractions at all.
- **Verify the return path before deleting.** `BackgroundJobsProvider` already polls across navigation and hydrates from `job.documents`; confirm that a doctor who leaves and returns still sees the extracted rows without the DB write. If that path has a hole, fix the hydration — do not keep the write to paper over it.

**If registration-time extraction must survive for some reason**, the minimum bar before it may write anything:

| Guard | Behaviour |
|---|---|
| Refuse when already verified | If `antibody_profile_verified` is True, **do not write**. Record a warning on the job: "this patient already has a verified profile; extracted rows are staged on the job for review." |
| Refuse when rows exist | Same treatment for any existing rows, verified or not. An unattended background task must never be the thing that removes clinical data. |
| Never flip verified → unverified | Downgrading the flag is itself a destructive act; it silently ejects the patient from the exchange pool. |

---

## J4. Fix 2 — make `replace_patient_antibody_profiles` recoverable

The general form of the bug outlives the auto-save. The **manual** endpoint `PUT /patients/{patient_id}/antibody-profiles` calls the same delete-and-reinsert, so any overwrite — human or machine — destroys the prior profile with no history.

Cheapest sufficient fix, no new table: **write the replaced rows into the existing audit log's `details` JSONB** before deleting them.

```python
details={
    "entry_count": len(entries),
    "previous_verified": previous_verified,
    "new_verified": new_verified,
    "replaced_entries": [{"antigen": p.antigen, "mfi": str(p.mfi)} for p in existing],
}
```

~100 rows of `{antigen, mfi}` is a few KB. It makes every overwrite recoverable by hand, which for data that gates transplant decisions is the minimum defensible standard. A dedicated history table is the better long-term answer; this is the version that ships this week.

---

## J5. Fix 3 — audit provenance

Both the OCR path and the manual path log `action="replaced_patient_antibody_profiles"` with `doctor_id`, and for the auto-save `doctor_id = job.doctor_id`. **An unattended background write is therefore indistinguishable from a doctor typing it in.** Only the `new_verified: false` transition hints at machine provenance.

Add `source` (`"ocr_job"` / `"manual"`) and `job_id` to `details`. If the auto-save is deleted per J3 this matters less, but the manual endpoint accepts `ocr_verified` as a query parameter and will keep carrying OCR-derived data.

---

## J6. Enhancement review — Worker queue: BackgroundTasks → Celery/Redis

**Settled in Part H. Verdict: no, and specifically not Celery.**

The stall this proposal targets is real but is caused by `run_extraction_job` holding a pooled DB connection across the entire multi-minute job against an untuned 5+10 pool — not by where the coroutine runs. Moving the same code into a Celery worker holds the same connection for the same eight minutes. And `OLLAMA_NUM_PARALLEL=1` on a CPU-only production box means there is no throughput to parallelise.

ARQ is deferred behind the written trigger in H9. See Part H.

---

## J7. Enhancement review — File handling: raw bytes → stream to disk / local S3

**Settled in Part G. Verdict: stream to disk, yes. Object storage, not yet.**

Agreed on the substance, with the caveat from G0 that the largest allocation is the decoded PIL bitmap in ocr-service, not the JPEG bytes in the backend — so spooling must be paired with the concurrency gate. MinIO is rejected for a single-host deployment and gated on the same trigger as the queue. See Part G.

---

## J8. Enhancement review — Table extraction: tiling → PaddleOCR / YOLO layout analysis

**Verdict: no as proposed — this is a revert of a deliberate migration two weeks old. But the idea underneath it is good, and there is a version that costs almost nothing.**

Commit `ec145ae` (2026-08-01), *"Migrate ocr-service from PaddleOCR to local vision-LLM (Ollama + qwen3-vl)"*, deleted `app/ocr/engine.py` and the column-clustering modules (`demographics.py`, `hla.py`, `mfi_extraction.py`, `crossmatch_extraction.py`, `geometry.py`, `common.py`) — they survive only under `_to_delete/ocr-service-paddleocr-migration-2026-08-01/`. The Dockerfile explicitly notes *"No OpenCV/PaddlePaddle system libraries needed anymore."* `ocr-service/pyproject.toml` is down to `fastapi, httpx, pillow, pydantic-settings, python-multipart, uvicorn`.

Reintroducing PaddleOCR or YOLO re-adds heavyweight dependencies and model weights that were just stripped, onto a CPU-only box already serialised behind Ollama. The rationale for that migration lives in `claude/ocr-to-local-llm-migration-plan.md`, which is outside the working tree — **read it before reversing anything in it.**

Also: the `"PaddleOCR can only process one image at a time"` comment in `ocr_batch_service.py` is a **stale leftover** from before the migration. It now happens to describe `OLLAMA_NUM_PARALLEL=1`. Fix the comment so nobody else reads it as evidence PaddleOCR is still in play.

**The cheap version of the good idea.** The real defect the proposal targets is that `make_row_band_tiles` cuts at blind arithmetic boundaries (`i * band_h`) that bisect table rows. That does not need a layout model:

```python
def find_row_cuts(image: Image.Image, num_tiles: int) -> list[tuple[int, int]]:
    # 1. grayscale -> binary ink mask
    # 2. horizontal projection: ink_per_row = mask.sum(axis=1)
    # 3. gutters = maximal runs where ink_per_row < eps
    # 4. snap each ideal boundary i*band_h to the nearest gutter centre
    # 5. fall back to the existing overlap only where no gutter is found
```

Pillow and numpy only — both already present. Deterministic, unit-testable, no weights, no GPU, ~50 lines. On a printed lab table the inter-row gutters are unambiguous.

The payoff compounds with Part I: when cuts land in gutters, **the overlap can shrink toward zero**, which removes the *cause* of the duplicate problem rather than reconciling it after the fact. Keep Part I's reconciliation regardless — belt and braces on clinical data — but this attacks the root.

**Sequencing: do Part I first.** Fix row identity and reconciliation, measure the residual error rate against the live harness, and only then decide whether row-aware cutting is worth building. Do not do both blind and lose the ability to attribute the improvement.

---

## J9. Enhancement review — Draft data: auto-save → JSON blob on the job record

**Verdict: agreed in direction; already built. See J0–J3.** The blob is `OcrExtractionJob.documents`. The work is deleting the write, not adding a table.

---

## J10. Enhancement review — Retry: re-prompt → constrained decoding (Guidance / Instructor / Outlines)

**Verdict: do the constrained decoding. Skip all three libraries — Ollama does it natively. And do not expect it to fix the failure that actually matters.**

Current state in `chat_json`:

```python
payload = {..., "format": "json", "stream": False, "think": False, ...}
...
raw_text = await _post(client, base_url, payload, label)
parsed = _try_parse_json(raw_text)
if parsed is not None:
    return parsed
payload["messages"].append({"role": "assistant", "content": raw_text})
payload["messages"].append({"role": "user", "content": "That wasn't valid JSON. Respond again with ONLY the JSON object, nothing else." + NO_THINK_SUFFIX})
```

`"format": "json"` is Ollama's **legacy free-form JSON mode**. Since v0.5, `format` accepts a **JSON Schema object** and constrains decoding via grammar. The spike README already requires Ollama ≥ 0.12.7. So:

- Pass a real JSON Schema in `format`. **Zero new dependencies.** Guidance, Instructor and Outlines all solve a problem the runtime already solves here; Instructor in particular targets OpenAI-compatible clients and would be a poor fit.
- The expected shapes are currently written **longhand inside the prompt strings** and exist nowhere machine-readable. Extracting them into real schemas is the prerequisite, and it pays for itself twice: constrained decoding **and** post-parse validation, which is almost entirely absent today. `_try_parse_json` only strips code fences and grabs the outermost `{...}`; nothing checks the 9-locus count the HLA prompt demands, and bead rows get only `_dedupe_rows` and `_coerce_mfi`.
- Keep the one-shot re-prompt as a fallback. Constrained decoding makes it rarer, not unnecessary.

**Two cautions, both important.**

1. **This does not fix the repetition loop.** An array containing the same row forty times is schema-valid. The documented *"six different labels all reported as the same 23706.91"* failure passes any schema you can write. Per Part I, that failure mode is detected by degenerate-tile heuristics and bead-ID coverage checks — not by the decoder. Do not let this enhancement create false confidence.
2. **Grammar constraints can degrade output quality on small models.** `qwen3-vl:4b-nothink` is a 4B model; forcing token selection can push it off a better completion. A/B it against `test_bead_specificity_live_scoring.py` before adopting — and note that per Part I that harness needs its own fix first, since its 15% MFI tolerance makes it blind to this bug class.

**Unrelated but adjacent: pin the Ollama image.** Compose uses `ollama/ollama:latest`. On a system producing clinical output, a `docker compose pull` can silently change model behaviour between two runs with no code change and no record. Pin the tag.

---

## J11. Sequencing across Parts G–J, and the Part F freeze

Dependencies that will cause problems if ignored:

1. **H3 (scope the DB session) before or with G8 (concurrency semaphore).** G8 applied to the current session structure turns a transient squeeze into a guaranteed stall — jobs queued on the semaphore each hold a connection. See H5.
2. **J3 (delete the auto-save) before I8 (null-MFI handling).** Deleting the write removes the crash path entirely, which makes I8 smaller.
3. **Part I before J8's row-aware cutting.** Fix identity, measure, then decide.
4. **Part I's harness fix before evaluating J10.** You cannot A/B constrained decoding with a scorer that has 15% MFI tolerance.

**On the Part F freeze.** F5 is titled *"OCR — reuse, do not rebuild"* and states *"No change to `ocr_batch_service.py`, `ocr_job_service.py`, the prompts, or the ocr-service at all."* Parts G, H and I all change exactly those files. That freeze was scoped to keeping Part F's feature work from turning into an OCR rewrite; G–I are defect fixes with different justification. **But reopen it consciously, not by accident** — add a note to F5 pointing at G–J so the next reader does not treat the contradiction as an error. F5.2's `hydratedDocTypesRef` dedup and network-blip retry are called load-bearing and must survive H8's polling backoff changes intact.

---

## J12. Tests

**Backend**

- `app/tests/integration/test_ocr_jobs.py` — the existing `patient_id` auto-save assertion **inverts**: a completed job with `patient_id` writes **nothing** to `antibody_profiles`, and the rows are readable from `job.documents`. This is the regression test for the whole part.
- A patient with an existing verified profile is **untouched** by a completed extraction job, and `antibody_profile_verified` stays True. Fails loudly today.
- `replace_patient_antibody_profiles` records `replaced_entries` in the audit log, and they round-trip well enough to reconstruct the prior profile.
- Audit `details` carries `source` and, where applicable, `job_id`.
- Unchanged: `PUT /patients/{id}/antibody-profiles` with `ocr_verified=None` preserves the prior flag (the Part E "no claim" contract).

**Frontend**

- `NewPairPage.jsx` no longer offers bead-specificity slots (F12).
- Leaving and returning to a registration in progress still shows extracted rows, hydrated from `job.documents` with no DB write.

**ocr-service (J10, if adopted)**

- The schema passed in `format` matches the shape the prompt describes — one test per document type, asserting the schema and the prompt cannot drift apart.
- A response that is schema-valid but contains 40 identical rows is **still** caught by Part I's degenerate-tile detection. This is the test that keeps constrained decoding from being mistaken for a correctness guarantee.

---

## J13. Do not

- **Do not build a `DraftRegistration` table.** `OcrExtractionJob.documents` is the staging layer and is already wired end-to-end.
- **Do not let a background task delete clinical data.** No unattended write may remove rows a human entered or verified — under any flag value.
- **Do not flip `antibody_profile_verified` from True to False automatically.** It silently ejects the patient from the exchange pool and hard-fails every compatibility check for them.
- **Do not reintroduce PaddleOCR or add YOLO** without first reading `claude/ocr-to-local-llm-migration-plan.md`. It reverses a deliberate two-week-old migration and re-adds dependencies that were explicitly stripped.
- **Do not add Guidance, Instructor or Outlines.** Ollama's `format` accepts a JSON Schema natively; the dependency buys nothing here.
- **Do not treat constrained decoding as a fix for the repetition loop.** Forty identical rows are schema-valid.
- **Do not adopt Celery.** See Part H — it does not fix the bug it is being proposed for.
- **Do not leave `ollama/ollama:latest` unpinned** on a system producing clinical output.
- **Do not delete the auto-save without confirming the hydration path.** If a returning doctor loses their extracted rows, fix the hydration; do not restore the write.
