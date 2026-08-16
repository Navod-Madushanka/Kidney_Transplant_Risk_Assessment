# Implementation prompt — Part F: pair-scoped documents and joint registration

**Insert as Part F of `implementation-prompt.md`, after Part E (record linking).** Read Part E first
— this part assumes the wizard is moving to linked records rather than creating them, and the two
parts share the same end state. Everything below the line goes to your coding agent.

---

## F0. The clinical fact this is built on

Look at the two lab reports this system actually consumes:

| Document | Who it covers | Issued |
|---|---|---|
| **Histocompatibility Type-match Report** (NBTS Colombo) | Patient **and** donor, side by side — name, NIC, DOB, blood group, and full 9-locus HLA typing for both | Once per pair, at workup |
| **Histocompatibility Report** — leukocyte crossmatch (NHK Kandy) | Patient **and** donor — demographics for both, plus T-cell / B-cell crossmatch and interpretation | Per pair, per assessment |
| **Bead Specificity Chart**, pages 1–2 | **Patient only** — one Sample ID, one Patient ID, no donor anywhere on the page | Per patient, periodically |

Two of the three documents are **pair documents**. The current model stores every document against a
single person, which forces a joint document to be filed under one side arbitrarily. The codebase
already knows this and works around it — `src/utils/resolvePrefillPhotos.js` says so out loud:

> *"The joint HLA typing / crossmatch reports (a single document covering both patient and donor) may
> have been archived under either side — prefer the patient's copy, fall back to the donor's. Bead
> specificity is a patient-only test."*

That fallback is a symptom. This part makes the ownership structural instead.

**The change in one sentence: documents are filed against whoever they are actually about — the pair,
or the patient — and a patient and their donor are registered together in one screen that reads the
two pair documents and fills the form in.**

---

## F1. Target ownership model

| Document category | Owner after this change | Uploadable from |
|---|---|---|
| `hla_typing_report` | **Pair** | Pair registration only |
| `crossmatch_report` | **Pair** | Pair registration only |
| `bead_specificity_chart_page_1` | **Patient** | Patient detail page |
| `bead_specificity_chart_page_2` | **Patient** | Patient detail page |
| `other` | Patient (retained for legacy rows) | Nowhere — hidden, see F10 |

**Donors own no documents at all.** Every donor-facing upload control is removed.

---

## F2. Backend — the pair record

### F2.1 New table

One Alembic migration, branched from the current head (`alembic heads` first).

`app/models/donor_patient_pair.py` → table `donor_patient_pairs`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `UUIDPrimaryKeyMixin` |
| `doctor_id` | UUID, not null, indexed | Owner, for scoping — same convention as `patients`/`donors` |
| `patient_id` | UUID FK → `patients.id`, not null, indexed | |
| `donor_id` | UUID FK → `donors.id`, not null, indexed | |
| `crossmatch_t_cell_result` | `String(50)`, nullable | Transcribed verbatim from the report |
| `crossmatch_b_cell_result` | `String(50)`, nullable | |
| `crossmatch_interpretation` | `Text`, nullable | The report's own conclusion sentence |
| `crossmatch_remarks` | `Text`, nullable | |
| `crossmatch_test_date` | `Date`, nullable | |
| `crossmatch_verified` | `Boolean`, not null, default `True` | Same OCR-confirmation contract as `hla_typing_verified` |
| `is_deleted` / `deleted_at` | Boolean / timestamptz | Mirrors `a1c3e5f7b9d1`'s soft-delete pattern |
| `created_at` / `updated_at` | timestamptz | `TimestampMixin` |

Partial unique index on `(patient_id, donor_id) WHERE is_deleted = false`, following the exact
pattern of `ix_donors_nic_number_active_unique` in migration `b2d4f6a8c0e3` — one active pair per
patient/donor combination, and soft-deleting one frees the combination for re-registration.

**There is deliberately no `crossmatch_is_positive` column.** See F5.3.

### F2.2 Reconciling with `Donor.intended_recipient_id`

`Donor.intended_recipient_id` already means "this donor is for this patient", and
`exchange_graph_service.load_exchange_pool` reads it directly to build the exchange pool. Adding a
pair table creates a second place the same relationship lives. Do **not** try to remove
`intended_recipient_id` — that would touch the matching engine, and this part should not.

Instead:

- `intended_recipient_id` stays the field the matching engine reads. Nothing in
  `exchange_graph_service.py`, `donor_search_service.py` or `donors.py` changes.
- Creating a pair **also sets** `donor.intended_recipient_id = patient_id`, in the same transaction.
- Add one invariant, enforced in `app/services/pair_service.py` and covered by a test: an active pair
  row's `(patient_id, donor_id)` must agree with that donor's `intended_recipient_id`. Raise, don't
  silently reconcile.
- Put a comment on both the column and the model saying which is authoritative for what. This
  redundancy is accepted on purpose; make sure the next reader knows that.

---

## F3. Backend — pair report files

### F3.1 The duplication problem, addressed once

`app/services/report_file_service.py` is already two near-identical halves — `create_patient_report_file`
/ `create_donor_report_file`, `list_*`, `get_*_by_id`, `delete_*`. A third copy for pairs would make
it three, at ~90 duplicated lines each.

**Before adding the third owner, extract the shared body.** The three functions differ only in the
model class and the owner column, so:

```python
async def _create_report_file(db, model, owner_field, owner_id, category, file, commit=True): ...
async def _list_report_files(db, model, owner_field, owner_id): ...
async def _get_report_file_by_id(db, model, owner_field, owner_id, report_file_id): ...
async def _delete_report_file(db, model, owner_field, owner_id, report_file_id, commit=True): ...
```

Keep the existing public `*_patient_*` / `*_donor_*` names as thin wrappers so no call site changes
in this step, and add `*_pair_*` alongside. This is a mechanical refactor with the existing
`test_report_files.py` as its safety net — do it as its own commit, before anything else in Part F.

### F3.2 New model and storage path

`app/models/pair_report_file.py` → `pair_report_files`, mirroring `PatientReportFile` exactly with
`pair_id` in place of `patient_id`, and the same `(pair_id, category)` uniqueness.

`_build_storage_path` already takes a `kind` string — pass `"pairs"`. No change to the path-safety
logic, which is already correct (server-generated uuid4 filename, client filename stored as display
metadata only).

### F3.3 Category validation per owner

Add to `app/models/enums.py`, next to `ReportFileCategory`:

```python
PAIR_REPORT_CATEGORIES = frozenset({
    ReportFileCategory.HLA_TYPING_REPORT,
    ReportFileCategory.CROSSMATCH_REPORT,
})
PATIENT_REPORT_CATEGORIES = frozenset({
    ReportFileCategory.BEAD_SPECIFICITY_CHART_PAGE_1,
    ReportFileCategory.BEAD_SPECIFICITY_CHART_PAGE_2,
})
```

Reject a category outside the owner's set with **422**, in the service layer, not the route — both
the pair-registration endpoint and the patient upload endpoint must be covered by the same check.
Enum-level validation alone is not enough: `ReportFileCategory` still contains every value, because
legacy rows reference them.

---

## F4. Backend — registration endpoint

New router `app/api/pairs.py`, prefix `/pairs`.

### F4.1 `POST /pairs` — register a patient, a donor, and the pair together

Request body (`app/schemas/pair.py`):

```python
class PairRegistrationRequest(BaseModel):
    patient: PatientCreate            # reuse, unchanged
    donor: DonorCreate                # reuse, unchanged
    patient_hla: list[HLATypingEntry] = []
    donor_hla: list[HLATypingEntry] = []
    crossmatch: PairCrossmatchInput | None = None   # t_cell / b_cell / interpretation / remarks / test_date
    ocr_verified: PairOcrVerified | None = None     # {details, hla_typing} — None = manual entry, trusted
```

Everything in **one transaction**, `commit=False` throughout, one `db.commit()` at the end, matching
`check_compatibility`'s existing pattern:

1. `create_patient(...)` — 409 on NIC conflict, same message as today.
2. `create_donor(...)` with `intended_recipient_id` set to the new patient's id.
3. Create the `DonorPatientPair` row, plus the crossmatch fields if supplied.
4. `replace_patient_hla_typing(...)` / `replace_donor_hla_typing(...)` with the `ocr_verified` flag.
5. One `create_audit_log(action="registered_pair", ...)` recording both ids and the entry source
   (`"ocr"` or `"manual"`).

A NIC conflict on either side must roll the **whole thing** back — half a pair is worse than none.
Note that `create_donor` will raise on a duplicate NIC too: `donors.nic_number` is globally unique
across active rows (`ix_donors_nic_number_active_unique`), not per-doctor like patients. Catch both
and return a 409 that says which side collided.

### F4.2 File upload endpoints

- `POST /pairs/{pair_id}/report-files` — multipart, `category` restricted to `PAIR_REPORT_CATEGORIES`.
- `GET /pairs/{pair_id}/report-files`
- `GET /pairs/{pair_id}/report-files/{id}/download`
- `DELETE /pairs/{pair_id}/report-files/{id}`

Scope every one through `get_pair_by_id_for_doctor(db, pair_id, doctor_id)`, 404 on miss — identical
in shape to `_ensure_patient_exists`.

### F4.3 Lookup endpoints

- `GET /pairs?patient_id=&donor_id=` — the pairs the current doctor owns, filterable. The patient and
  donor detail pages use this to render their read-only pair-documents section.
- `GET /pairs/{pair_id}` — pair plus both summaries plus the stored crossmatch.

---

## F5. OCR — reuse, do not rebuild

> **Note (Part J, J11):** F5.1's "no change to `ocr_batch_service.py`, `ocr_job_service.py`, the
> prompts, or the ocr-service at all" was scoped to keeping *this part's* feature work from turning
> into an OCR rewrite. Parts G, H, I and J all subsequently change exactly those files — bounded
> memory (G), the DB connection-pool bug (H), bead-row identity/tile reconciliation (I), and deleting
> the unattended antibody-profile write (J). That's not a contradiction: G–J are defect fixes with
> their own justification, landed after this part, not a violation of the freeze stated below. F5.2's
> `hydratedDocTypesRef` dedup and network-blip retry are called load-bearing there too, and did
> survive H's polling-backoff changes intact.

### F5.1 No new extraction code

`POST /ocr/extract-batch/jobs` already accepts each of its four slots independently
(`_build_files_payload` in `app/api/ocr.py` filters to the ones actually provided). The pair flow
posts **only** `hla_typing_report` and `crossmatch_report` and gets back exactly what it needs. No
change to `ocr_batch_service.py`, `ocr_job_service.py`, the prompts, or the ocr-service at all.

Confirm before building that this is what the prompts already return — it is:

| Slot | Returns |
|---|---|
| `hla_typing_report` | `patient_details`, `donor_details`, `patient_hla` (9 loci), `donor_hla` (9 loci) |
| `crossmatch_report` | `patient_details`, `donor_details`, `crossmatch{t_cell_result, b_cell_result, interpretation, remarks, test_date}` |

`stream_batch_extraction`'s crossmatch branch already applies **gap-fill precedence** — it only
contributes a demographic field the HLA typing report did not already find. That is exactly the
behaviour this flow wants; do not change it.

### F5.2 Generalise the polling hook

`src/hooks/useExtractionJobPolling.js` currently dispatches `WIZARD_ACTIONS.HYDRATE_FROM_OCR` into
the wizard reducer, which hard-couples it to the wizard. Change the signature to take callbacks:

```js
useExtractionJobPolling({ jobId, status, onDocumentDone, onStatusChange })
```

Have `WizardProvider` pass the two dispatches it makes today. The pair page passes its own local
setters. Keep the `hydratedDocTypesRef` de-duplication and the retry-on-network-blip behaviour
exactly as they are — both are load-bearing.

### F5.3 The crossmatch result

The OCR'd T-cell / B-cell / interpretation / remarks / test-date values are stored on the pair and
prefill Step 6 of the compatibility check.

**`is_positive` is never OCR-filled and is never stored on the pair.** It is the doctor's own reading,
entered on the Review step, and it is what actually gates Step 6 — the comment in
`wizardReducer.js`'s `crossmatch` block already states this contract and it must survive this part
intact. The wizard prefills the text fields and shows the stored interpretation sentence as context;
the positive/negative control still starts empty and still blocks submission until set. A doctor
re-running a check re-confirms, which is correct for a same-day result.

---

## F6. Frontend — the registration page

New route `/pairs/new`, page `src/pages/NewPairPage.jsx`, linked from the sidebar as the primary way
to add people. Layout top to bottom:

### 1. Documents (top of the page, as specified)

Four `FileUpload` slots, in this order:

| Slot | Extracted? |
|---|---|
| Histocompatibility Type-match Report | **Yes** |
| Histocompatibility / Crossmatch Report | **Yes** |
| Bead Specificity Chart — Page 1 | No — archived to the patient |
| Bead Specificity Chart — Page 2 | No — archived to the patient |

Label the bead slots clearly as *"Stored for the compatibility check — not read now"*, so it is
obvious why two of the four uploads do not contribute to the form below. A bead chart takes several
minutes per page to extract and its values are not needed to create a record; reading it here would
make registration slow for no benefit.

An **"Extract details"** button, enabled once at least one of the two extractable documents is
attached. It posts those documents to `POST /ocr/extract-batch/jobs` and shows the same per-document
progress list `PhotoUploadsStep.jsx` already renders — lift that progress list into a shared
component rather than copying it.

### 2. Patient section

`PatientForm`, prefilled from `patient_details` + `patient_hla`. Plus the HLA typing editor rows.

### 3. Donor section

`DonorForm`, prefilled from `donor_details` + `donor_hla`. **No upload control anywhere in it.**

### 4. Confirmation

Two toggles, using the existing `ToggleSwitch` and the same contract as `HlaTypingStep.jsx`: one for
the demographics, one for the HLA typing. Shown **only when OCR actually ran** — a doctor who typed
everything by hand has nothing to confirm. Submit is blocked while an OCR-populated group is
unconfirmed.

### 5. Submit

`POST /pairs`, then upload all four files (two to the pair, two to the patient), then navigate to the
new patient's detail page.

Make the uploads **resumable in the same style as `submitCompatibilityCheck`** — a progress object,
each step skipped if already done, the error carrying `err.progress`. A 20 MB upload failing on a
hospital connection must not force the doctor to re-enter the whole form.

### What OCR cannot give you

Neither document prints sex, weight, or any of the donor clinical panel. Those stay manual fields on
the form, and they are exactly the inputs LKDPI and the Grams donor-risk model need (Part E, §E0).
Registering a pair through this screen is therefore the natural moment to capture them — surface
`PatientForm`'s sex/weight and `DonorForm`'s full clinical panel here, with a short note that leaving
them blank means those two scores will be withheld rather than estimated.

---

## F7. Frontend — what shrinks

### `DonorDetailPage.jsx`

Delete the `<ReportFilesCard>` block (~line 311) and its four imports from `api/reportFiles.js`.
Replace with a read-only **Pair documents** card: the pair's two documents with download buttons, no
upload control, no delete, and a line naming the linked patient.

### `PatientDetailPage.jsx`

Keep `<ReportFilesCard>` but restrict it to the two bead slots, and add the same read-only pair card.

### `ReportFilesCard.jsx`

Currently maps `REPORT_FILE_CATEGORY_OPTIONS` unconditionally. Add a required `categories` prop and
map that instead. The patient page passes the two bead categories. Nothing else about the component
changes — the slot mechanics, replace-on-upload and delete confirmation are all fine as they are.

### `constants/reportFileCategory.js`

Split the flat list into `PAIR_REPORT_CATEGORY_OPTIONS` and `PATIENT_REPORT_CATEGORY_OPTIONS`, keeping
`reportFileCategoryLabel()` covering every value including the legacy ones.

### `utils/resolvePrefillPhotos.js`

`allowDonorFallback` becomes dead once donors own no files. Change the two joint slots to resolve
from the **pair's** files, and the two bead slots from the patient's. The function stays pure; only
its inputs change — `resolvePrefillPhotos(pairFiles, patientFiles)`.

### Keep, but demote

`NewPatientPage` and `NewDonorPage` stay. A donor with no assigned recipient is a real case — it is
what feeds cross-hospital search (`donor_search_service.py` pools only donors with
`intended_recipient_id IS NULL`) and it must remain registrable. Move both behind a secondary
"Register individually" link and make `/pairs/new` the primary sidebar action.

---

## F8. Downstream: the compatibility check

With pair documents on the pair and demographics captured at registration, the wizard's photo step
has almost nothing left to do. Combined with Part E, it becomes:

1. **Select the pair** (Part E §E3.3) — or arrive with it preselected.
2. **Bead specificity** — the only extraction left in the wizard, prefilled from the patient's
   archived pages. This is what the user means by keeping the bead reports for check time: the
   antibody screen is the part that changes between assessments.
3. **Sensitisation**, **crossmatch confirmation**, **review** — unchanged, except that Step 6's text
   fields arrive prefilled from the pair.

`PhotoUploadsStep.jsx`'s `UPLOAD_SLOTS` drops from four entries to two. Do this **after** Part E
lands, not alongside it — Part E changes the same submission path, and doing both at once makes the
regression surface hard to reason about.

---

## F9. Two small defects the real documents expose

### F9.1 Rh factor is thrown away

Both reports print the blood group as **"B Positive"**. `parseOcrBloodType` in
`src/utils/ocrNormalize.js` matches only `^(AB|A|B|O)` and discards the rest, and `normalizeOcrBatchResponse`
never populates `rh_factor` — yet `rh_factor` is **required** on `PatientCreate` and `DonorCreate`.
So the doctor is forced to re-enter, by hand, a value that is printed on the page the system just
read.

Add `parseOcrRhFactor(raw)` handling `Positive` / `Pos` / `+` → `"+"` and `Negative` / `Neg` / `-` →
`"-"`, empty string when absent, and populate `rh_factor` in both detail objects. Unit-test it
against the literal strings on these two reports.

### F9.2 NIC case and format

The four reports carry NICs in both formats and both cases: `198001610076`, `823275544v`,
`765811562V`, `199315003570`. The uniqueness indexes are exact-match and case-sensitive, so
`823275544v` and `823275544V` are two different people as far as Postgres is concerned.

Normalise the old-format trailing letter to uppercase on write, in the schema validator, so OCR
output and hand entry converge. Do **not** attempt old-format-to-new-format conversion — that needs
the birth year and a day-of-year offset, and getting it wrong silently merges two patients.

### F9.3 Do not extract the lab's own prognosis

The type-match report's Remarks field carries the issuing lab's own interpretation — a hazard ratio
and a graft-survival estimate in years. It is not one of the extraction targets and must not become
one. This system computes its own risk layer from published models with its own citations; ingesting
a second, differently-derived prognosis as data would put two unreconciled numbers on the same
report.

---

## F10. Existing data

Order matters — run these as separate, reviewable migration steps:

1. **Create** `donor_patient_pairs` and `pair_report_files`.
2. **Backfill pairs** from `donors WHERE intended_recipient_id IS NOT NULL AND is_deleted = false`,
   one pair row per donor, `doctor_id` from the donor.
3. **Move joint documents.** For each `patient_report_files` / `donor_report_files` row in category
   `hla_typing_report` or `crossmatch_report`, move it to the pair if exactly one active pair can be
   inferred for that person. Rows that resolve to zero or more than one pair are **left in place and
   logged** — do not guess which pair a document belongs to. Move DB rows only; the on-disk path is
   already a stable uuid, so leave the bytes where they are and update `storage_path` if you change
   the `kind` prefix, or leave the prefix alone and accept that legacy files sit under `patients/`.
4. **Report** what moved and what did not, in the migration's own output.

If this is still pre-production with no real patient data, say so and take the simpler route: drop
and recreate. Confirm which situation applies before writing the backfill — it is a lot of care for
an empty table.

---

## F11. Tests

**Backend**

- `test_pairs.py` — registration creates patient, donor, pair, both HLA typings and one audit entry
  in a single transaction; a NIC conflict on the donor rolls back the patient too (assert zero rows
  of each); `intended_recipient_id` is set and matches the pair.
- `test_pairs.py` — uploading `bead_specificity_chart_page_1` to a pair returns 422; uploading
  `hla_typing_report` to a patient returns 422.
- `test_pairs.py` — a second active pair for the same (patient, donor) returns 409; soft-deleting the
  first allows it.
- `test_pairs.py` — another doctor's pair 404s on every pair endpoint.
- `test_report_files.py` — unchanged and still green after the F3.1 refactor. This is the safety net
  for that refactor; run it before and after.

**Frontend**

- `NewPairPage.test.jsx` — the two bead slots do not appear in the extraction request; submit is
  blocked while an OCR-populated group is unconfirmed; a failed file upload preserves the created
  ids so retry does not re-create the patient.
- `ocrNormalize.test.js` — `parseOcrRhFactor` against `"B Positive"`, `"B Negative"`, `"O+"`, `""`.
- `DonorDetailPage.test.jsx` — no upload control renders anywhere on the page.
- `resolvePrefillPhotos.test.js` — updated for the pair/patient split; the donor-fallback cases are
  deleted, not left asserting old behaviour.

---

## F12. Do not

- **Do not remove `Donor.intended_recipient_id`.** The matching engine reads it. The pair record adds
  storage on top; it does not replace that relationship. See F2.2.
- **Do not extract the bead chart during registration unguarded.** A registration-time background
  extraction job (added 2026-08-14) auto-saved its result straight to `antibody_profiles` with no
  guard, and could silently destroy an already-verified profile — see `implementation-prompt-part-j.md`
  J0–J3, which deleted it entirely. It was deliberately restored afterward (explicit product decision,
  not a reversal of the finding): the job and its global progress toast are back, but the auto-save
  now refuses to write whenever the patient already has any antibody-profile rows, verified or not —
  see `ocr_job_service.py`'s `_save_bead_specificity_if_present`. The bug was the missing guard, not
  extracting-at-registration itself.
- **Do not let OCR set `crossmatch_is_positive`.** There is no such column, and there should not be.
- **Do not add a third hand-written copy of the report-file CRUD.** Extract the shared body first
  (F3.1) — that refactor is a precondition, not a nice-to-have.
- **Do not delete `NewPatientPage` / `NewDonorPage`.** Unassigned donors are what the cross-hospital
  pool is made of.
- **Do not do this at the same time as Part E.** Both rewrite the wizard's submission path. Land Part
  E, get it green, then start here.
