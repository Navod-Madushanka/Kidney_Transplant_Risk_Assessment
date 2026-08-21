# Finalization plan — Kidney Transplant Compatibility System

**Audited 21 August 2026 against the working tree at HEAD `6df7d06` ("Bug fix").**
**Target: a real hospital pilot with real patients.** Every recommendation below is
graded against that bar, not against a demo or a submission.

Everything in the "Verified state" section was produced by executing the code in this
audit, not by reading it. Every bug in Part 2 has a reproduction you can run.

---

## Part 0 — Verdict

**The engineering is strong. The clinical reasoning layer is where the risk is.**

This codebase is better than most production systems: 832 green tests, a hash-chained
audit log, honest provenance docstrings on every clinical constant, and a
`docs/clinical-basis.md` that openly separates "externally citable" from "came from our
project spec." The previous review's entire P0/P1 list has been closed — registration is
shut, `/auth/me` exists, CORS is env-driven, `ollama` has a memory limit, both lint gates
are green.

What is **not** ready for real patients is narrower and more serious than a long to-do
list. There are **two defects that cause the system to give a clinically wrong answer
silently**, and both are reachable through the normal UI:

1. A pairing whose HLA typing was never entered is reported to the doctor as
   **"Not Compatible — Too many HLA mismatches"**, quoting six mismatches that were never
   measured.
2. A donor-specific antibody at MFI 12,000 — well past the threshold that is supposed to
   halt the transplant — is **completely invisible** to the DSA safety gate if the doctor
   types it in the format the app's own on-screen example tells them to use.

Neither is a crash, neither fails a test, and neither looks wrong on screen. Those are
the two things to fix before anything else.

On the doctors' comment about medical wording: they are right, and it goes deeper than
labels. Part 3 is a complete glossary. Two of the wording problems (**"High Genetic
Risk"** and the **allele-vs-antigen** placeholder) are not cosmetic at all — the second
one *is* defect #2 above.

**Estimated effort to pilot-ready: 3–4 focused weeks**, of which about one week is
blocked on decisions only the doctors can make.

---

## Part 1 — Verified state

Run in this audit, in a clean container against a real PostgreSQL 16:

| Check | Result |
|---|---|
| `kidney-backend` tests | **502 passed**, 0 failed (213 s, real Postgres 16) |
| `kidney-frontend` tests | **252 passed**, 0 failed (34 files) |
| `ocr-service` tests | **78 passed**, 0 failed (4 live-Ollama tests correctly deselected) |
| **Total** | **832 passing, 0 failing** |
| `ruff check .` | **All checks passed** — the 70 errors in the last review are gone |
| `npx eslint .` | **Clean** — the 16 errors in the last review are gone |
| Test warnings | **416**, all PuLP deprecations (see B11) |

Closed since the last review, confirmed in the tree: `POST /auth/register` removed;
`create_doctor` / `promote_admin` operator scripts exist and are audited; CORS env-driven;
`GET /auth/me` implemented; `ollama` `mem_limit: 6g`; `docker-compose.prod.yml` and
`.env.example` complete; exchange accept/decline has both `.catch()` and a confirmation
modal; the `cpra_fraction` raw-vs-normalised bug is fixed (`exchange_graph_service.py:324`
now normalises before building the index).

---

## Part 2 — Defects

Ranked by clinical consequence. Each has a reproduction.

---

### B1 — CRITICAL — Missing HLA typing is reported as "Not Compatible"

**Files:** `kidney-backend/app/services/hla_mismatch_service.py:105`,
`kidney-backend/app/services/report_outcome_service.py:107`,
`kidney-backend/app/reference_data/report_outcome.py` (decision table row 1)

`calculate_mismatch_result` deliberately imputes the **maximum** 2 mismatches for any
locus whose typing is absent — a sound conservative choice, and it correctly sets
`data_completeness=False`. But three untyped loci sum to exactly 6, which trips
`is_halted = total_mismatches >= MAX_ACCEPTABLE_MISMATCHES`, and the pipeline returns
`halted_mismatch_reject`. The outcome decision table matches `halted_*` on **row 1**,
which fires **before** the `data_completeness` check on row 3. The completeness flag is
never consulted.

**Reproduction (run from `kidney-backend/`):**

```python
from app.services.hla_mismatch_service import calculate_mismatch_result
from app.services.report_outcome_service import build_report_outcome
from dataclasses import asdict

r = calculate_mismatch_result({}, {})          # nothing typed on either side
o = build_report_outcome(
    overall_status="halted_mismatch_reject",
    abo_result={"recipient_type": "A", "donor_type": "O", "is_compatible": True},
    mismatch_result=asdict(r),
)
print(o.verdict_label, "|", o.headline, "|", o.detail)
```

**Actual output:**

```
Not Compatible | Too many HLA mismatches |
6 HLA mismatches across A/B/DRB1 (bucket: 3-6 mismatches) — above the acceptable threshold.
```

Zero mismatches were measured. The report states six as fact, names the bucket, and
attaches **no review flags at all**. A doctor reading this is told a pairing was rejected
on evidence that does not exist.

The same thing happens with *partial* data: patient fully typed, donor DRB1 missing, four
genuine A/B mismatches → 4 measured + 2 imputed = 6 → "Not Compatible."

**Fix:**

1. In `calculate_mismatch_result`, never set `is_halted=True` when
   `data_completeness is False`. Incomplete data cannot reject a pairing.
2. Add a row to the outcome decision table **above** the `halted_*` row: if
   `mismatch_result.data_completeness is False`, the verdict is `cannot_assess`, headline
   "HLA typing incomplete", detail listing `mismatch_result.missing_inputs` verbatim.
3. When any locus was imputed, the detail line must never quote a total as though it were
   measured. Say "4 mismatches measured at A and B; DRB1 not typed."
4. Enforce completeness at the API boundary too — see B3.

**Acceptance:** a test asserting that an all-untyped pair yields `cannot_assess`, that its
detail names every missing locus, and that no `detail` string quotes a total containing
imputed mismatches.

---

### B2 — CRITICAL — A strong DSA is silently invisible if entered allele-level

**Files:** `kidney-frontend/src/pages/BeadSpecificityStep.jsx:232`,
`kidney-backend/app/schemas/antibody_profile.py`,
`kidney-backend/app/services/hla_typing_service.py:105`

The matching pipeline works entirely at **serological antigen** level: donor typing rows
become `B44` via `hla_antigen_designation`, and antibody antigens are compared by exact
string match. `normalize_antibody_antigen`'s own docstring states that allele-level
designations like `B*07:02` are "a different, unmapped naming scheme entirely."

The manual bead-entry screen's placeholder is **`"Antigen (e.g. B*44:02)"`** — an
allele-level example. The `AntibodyProfileEntry` schema types `antigen` as a bare `str`
with no validation. So the app instructs the doctor to enter data in a format it cannot
match, and accepts it without complaint.

**Reproduction (run from `kidney-backend/`):**

```python
from app.services.hla_typing_service import normalize_antibody_antigen, hla_antigen_designation
from app.services.dsa_service import check_dsa, PatientAntibody

antibody = normalize_antibody_antigen("B*44:02")   # what the doctor typed
donor     = hla_antigen_designation("B", "44")     # what the donor's typing row becomes
print(antibody, donor, antibody == donor)

r = check_dsa([PatientAntibody(antigen=antibody, mfi=12000.0)], [donor])
print("halted:", r.is_halted, "matches:", r.matches)
```

**Actual output:**

```
B*44:02 B44 False
halted: False matches: []
```

An MFI 12,000 donor-specific antibody — 2.4× the "strong" halting threshold — produces
**no match, no halt, no warning**. The pipeline proceeds to crossmatch and can return
"Compatible." The same antibody entered as `B44` halts correctly.

The OCR path is not affected: `ocr-service/app/llm/prompts.py:189` correctly instructs the
model to read the **Sero** column and explicitly not the "Allele Equiv" column. This is
purely the manual-entry path, caused by the app's own example text.

**Fix:**

1. Change the placeholder to a serological example: `"Antigen (e.g. B44)"`. Match
   `AntibodyProfileEditor.jsx:118`, which already gets this right (`"Antigen (e.g. DQ7)"`).
2. Add a validator on `AntibodyProfileEntry.antigen` that **rejects** allele-level input
   (any `*` or `:`) with a message naming the expected format and the serological
   equivalent. Silent acceptance is what made this dangerous.
3. Add the same validation on the frontend field so the doctor sees it before submitting.
4. Add a regression test asserting that a high-MFI antibody which fails to match any donor
   antigen **cannot** silently pass — either it matches, or the report carries an explicit
   "antibody specificity not matched to any donor antigen" review flag.

**Point 4 is the durable fix.** Even with validation, any antibody the system cannot map
to a donor antigen must be surfaced, never dropped.

---

### B3 — HIGH — `POST /compatibility/check` does not enforce typing completeness

**File:** `kidney-backend/app/api/compatibility.py:57`

The endpoint blocks only on `unverified_data_reasons` — the OCR `*_verified` flags. It
never checks typing *completeness*. That check exists only in
`build_compatibility_readiness`, which powers the wizard's preview panel. Anything that
does not go through the wizard — the Swagger UI at `/docs`, a script, a future mobile
client, a doctor who navigates directly — reaches `run_match_pipeline` with empty typing
and gets B1's wrong answer.

**Fix:** hoist the completeness check into the endpoint's precondition block alongside the
existing unverified-data guard, returning 422 with the `missing_inputs` list. The
readiness endpoint stays as the friendly preview; the API stops depending on the UI for
safety.

---

### B4 — HIGH (clinical) — Crossmatch is a single boolean

**Files:** `kidney-backend/app/services/crossmatch_service.py`,
`kidney-backend/app/schemas/match_report.py` (`CrossmatchInput`)

`is_positive: bool` → halt. `t_cell_result` and `b_cell_result` are captured as free text
and never read by any logic. Clinically these are not interchangeable:

- A positive **T-cell CDC** crossmatch is an absolute contraindication.
- A positive **B-cell flow** crossmatch with a negative T-cell CDC is frequently proceeded
  with, and often reflects autoantibody or non-HLA reactivity.
- **CDC** and **flow cytometry** crossmatch have different sensitivities and different
  clinical weight; the system does not record which was performed.

Collapsing all of that into one boolean means the app either over-rejects viable pairings
or under-rejects dangerous ones, depending on how the coordinator interprets the checkbox.

**Fix:** this is a **clinical design question, not a code change** — take it to the doctors
(see Part 5, Q3). Do not invent the rule. What can be built now: capture method (CDC /
flow / both), cell type, and result as structured enums rather than free text, so whatever
rule they specify has real inputs to act on.

---

### B5 — MEDIUM-HIGH — DSA screening silently ignores untyped donor loci

**File:** `kidney-backend/app/services/match_pipeline.py:243`

`donor_hla_antigens` is built only from donor typing rows that exist. If the donor has no
DQB1 typing, a patient's anti-DQ antibody at any MFI cannot match — and unlike Step 3, the
DSA step reports **no incompleteness flag at all**. A missing DQ typing paired with an
anti-DQ DSA is a classic cause of an unexpected positive crossmatch.

**Fix:** have `check_dsa` return the set of loci actually screened. When a patient carries
antibodies against a locus the donor has no typing for, attach a review flag naming that
locus. Same "never let absent data read as a negative result" principle already applied
correctly in `hla_mismatch_service`.

---

### B6 — MEDIUM — Two pages fail silently on submit

**Files:** `kidney-frontend/src/pages/NewPatientPage.jsx:13-19`,
`kidney-frontend/src/pages/NewDonorPage.jsx:12-20`

Both use `try { … } finally { setIsSubmitting(false) }` with **no `catch`**. A duplicate
NIC (a 409 from the uniqueness constraint) becomes an unhandled promise rejection: the
button stops spinning and nothing else happens. The doctor cannot tell whether the record
saved.

The equivalent bug on the exchange pages **has** been fixed — `ExchangeProposalDetailPage`
and `ExchangeProposalsInboxPage` now have both `.catch()` and confirmation modals. These
two were missed.

**Fix:** add `.catch()` with an inline error surfacing the API's message, matching the
pattern already used in `ExchangeProposalDetailPage.jsx:95`.

---

### B7 — MEDIUM — Duplicate `/auth/me` route

**Files:** `kidney-backend/app/main.py:118`, `kidney-backend/app/api/auth.py:49`

Two handlers register the same path. The router's version wins because
`include_router(auth_router)` runs first, and it is the correct one — it returns
`hospital_name` and `is_admin`. The copy in `main.py` returns neither.

Nothing is broken today. But it is a live trap: reordering the router includes, or a merge
that moves the block, silently strips the admin flag and hospital name from every session,
and the sidebar and Audit Log nav item quietly stop working.

**Fix:** delete the handler in `main.py`. Add a startup assertion that no path is
registered twice.

---

### B8 — MEDIUM (governance) — Patient-shaped identifiers in tracked files

**Files:** `kidney-backend/app/tests/integration/test_ocr_jobs.py:31`,
`kidney-backend/app/tests/unit/test_ocr_batch_service.py` (5 occurrences),
`kidney-frontend/src/pages/PhotoUploadsStep.test.jsx` (3 occurrences),
`ocr-service/app/tests/fixtures/hla_typing_ground_truth.json:5`

`"Rev.S.Amarasinghe Thero"` with NIC `198723456789` — a realistic Sri Lankan name and a
structurally valid NIC. The previously-flagged `Rev.A.Premarathna` / `198001610076` is
gone, so this was partly remediated; this one remains in six files.

For a real pilot this is a **Personal Data Protection Act No. 9 of 2022** question, not a
tidiness question. Whether or not this particular record is real, a data-protection review
will ask, and "it's test data" is a weaker answer than not having it there.

**Fix:** replace with obviously-synthetic identities (`Test Patient One`, NIC
`200000000001`) across all six files plus the OCR ground-truth fixture. Confirm the 20 real
lab-report JPEGs under `kidney-backend/uploads/report_files/` are handled under a documented
data-use basis before the pilot, and add a CI grep that fails on NIC-shaped literals
outside an allowlisted synthetic range.

---

### B9 — MEDIUM — No transport security, no login throttling

**Files:** `docker-compose.prod.yml` (no TLS anywhere),
`kidney-frontend/src/api/client.js:17` (JWT in `sessionStorage`),
`kidney-backend/app/api/auth.py:24`

For a demo these were acceptable. For real patient data on a hospital network they are not:

- **No TLS.** Credentials and full patient records cross the network in cleartext. The
  compose file exposes 8000 and 3000 over plain HTTP with no reverse proxy.
- **No rate limiting or lockout** on `POST /auth/login`. Unlimited password attempts.
- **JWT in `sessionStorage`**, readable by any script on the page.
- **60-minute expiry, no refresh** — a session dies mid-consultation with no warning.

**Fix, in priority order:** (1) TLS-terminating reverse proxy in the compose file, with
HSTS and the standard security headers; (2) per-IP and per-account throttling with
exponential backoff on login, audited; (3) session expiry warning with re-auth. Moving the
token out of `sessionStorage` to an httpOnly cookie is a larger change — worth doing, but
after TLS exists, since without TLS it buys nothing.

---

### B10 — MEDIUM — `create_doctor` takes the password as a CLI argument

**File:** `kidney-backend/app/scripts/create_doctor.py:78`

`uv run python -m app.scripts.create_doctor <email> <password> "<name>"` puts the password
in shell history and in the process table, where any user on the host can read it with
`ps`. The README documents this as the account-creation procedure.

**Fix:** read the password from a no-echo prompt (`getpass`) or stdin. Keep the 8-character
minimum but add a real policy — length ≥ 12, and a check against a common-password list.
Update the README.

---

### B11 — MEDIUM (upgradability) — PuLP will break the exchange solver

**File:** `kidney-backend/pyproject.toml:19` — `"pulp>=3.3.2"`, unpinned upward

All 416 test warnings are PuLP deprecations: `LpVariable(...)` direct construction and
`PULP_CBC_CMD`. **Both are removed in PuLP 4.0.** The dependency has no upper bound, so an
unlucky `uv sync` on a fresh machine silently installs 4.0 and the entire paired-exchange
optimiser stops working.

**Fix:** pin `pulp>=3.3.2,<4.0` **today** — one line, removes the landmine. Then migrate to
`prob.add_variable(...)` and `COIN_CMD` as a separate, tested change, and lift the ceiling
once the 416 warnings are zero.

---

### B12 — MEDIUM (maintainability) — Unit tests require a live database

**File:** `kidney-backend/app/tests/conftest.py:68`

`_test_schema` is `scope="session", autouse=True`, so it runs for **every** test in the
tree — including the pure-function suites (`test_risk_tier_service.py`,
`test_risk_classification.py`, `test_sensitization_service.py`, `test_cpra_service.py`)
that touch no database at all. Without Postgres reachable, all 264 unit tests error at
setup rather than running.

This matters directly for what comes next: the clinical constants in Part 5 are exactly
what the doctors will revise, and revising them should be a five-second feedback loop, not
a Docker-dependent one.

**Fix:** split into `app/tests/unit` (no DB fixture, runs standalone) and
`app/tests/integration` (DB-backed), with the autouse fixture scoped to the integration
package only. Add `pytest app/tests/unit` as a fast pre-commit gate.

---

### B13 — LOW-MEDIUM (upgradability trap) — Risk-tier bands have gaps

**File:** `kidney-backend/app/reference_data/risk_tiers.py:18-23`

The bands are `0.0–2.0`, `2.25–5.0`, `5.25–7.0`, `7.25–10.0`. A score of `2.1`, `5.1` or
`7.1` falls in **no band** and `get_risk_tier` raises `ValueError`. This is unreachable
today only because every weight in `HLA_LOCUS_WEIGHTS` is a multiple of 0.25.

`match_pipeline.py:345` wraps the call in `try/except ValueError`, so it degrades to
`risk_tier = None` rather than a 500 — but that null is indistinguishable from "incomplete
typing," so the failure is silent.

The trap: **the first thing the doctors are likely to change is a locus weight.** Any
non-quarter weight starts silently suppressing the risk tier for a band of scores.

**Fix:** make the bands contiguous half-open intervals (`min <= score < max`, top band
inclusive) and add a startup assertion that they cover `[0, max_possible_score]` with no
gap and no overlap. Test the boundaries.

---

### B14 — LOW — Antibody panel class is inferred from upload slot

**File:** `kidney-backend/app/models/enums.py` (`AntibodyPanel`),
`kidney-backend/app/services/ocr_batch_service.py` (`SLOT_PAGE_PANEL`)

Page 1 → Class I, page 2 → Class II, by position. If a lab prints them in the other order,
or a doctor uploads the pages swapped, every row is labelled with the wrong class and
`(panel, bead_id)` row identity silently collides. Nothing validates the label against the
antigens actually on the page.

**Fix:** cross-check the assigned panel against the extracted antigen names (A/B/C → Class
I; DR/DQ/DP → Class II) and raise a conflict for the doctor to resolve, rather than trusting
slot position.

---

### B15 — LOW — No structured logging

`kidney-backend` configures no logging at all. The hash-chained audit log covers clinical
actions well, but there is no operational log for diagnosing a failed extraction or a 500
in the pilot. Add structured JSON logging with a request ID, and make sure it never logs
patient identifiers or antigen data.

---

## Part 3 — Medical terminology

**This is the section to hand a coding agent verbatim.** Apply it as a mechanical pass,
then have the doctors review the result.

Two entries are **not** cosmetic — **T1** and **T9** — and T9 is the same defect as B2.

### Standing instructions for the agent

- Sri Lanka follows **British/Commonwealth clinical English**. Use `-ise`/`-isation`
  spellings throughout (`sensitised`, `desensitisation`, `normalised`). The codebase
  currently mixes both, sometimes in the same file.
- **Do not rename a database enum value, a stored JSON key, or an API field** as part of a
  wording change. Change the *display label*, the *docstring*, and the *comment*. Where a
  Python identifier is genuinely wrong (T2), rename the identifier but keep the wire format
  stable and add a migration note.
- **Every changed clinician-facing string must be listed in a review document for the
  doctors to sign off.** Do not treat this pass as complete when the code compiles.

### Glossary

| # | Currently says | Should say | Where | Why it is wrong |
|---|---|---|---|---|
| **T1** | **"High Genetic Risk"** | **"High Immunological Risk"** | `reference_data/risk_tiers.py:22`; `components/ui/Badge.jsx:27` | **Materially wrong.** HLA mismatch is *immunological* risk. "Genetic risk" means inherited disease predisposition — a doctor reads this as a screen for heritable disease. Highest-priority wording fix. |
| **T2** | `sensitized_antigens` | `unacceptable_antigens` | `services/cpra_service.py:17,37,58`; `services/antibody_profile_service.py:121`; `services/match_pipeline.py:215` | The *patient* is sensitised; the antigens are **unacceptable antigens** — the standard cPRA input term. "Sensitized antigens" is not a thing. |
| **T3** | mixed `sensitized` / `sensitised` | `sensitised` everywhere | many files, incl. user-facing `report_outcome.py:75` | Two spellings appear inside one clinical report. |
| **T4** | "ESRD" / "end-stage renal disease" | **"kidney failure"** (or "ESKD") | `reference_data/donor_risk_model.py:3,15`; `services/donor_risk_service.py:5,19`; `models/donor.py:86` | KDIGO 2020 consensus nomenclature retired "renal" and "ESRD". Grams' own paper title says "Kidney-Failure Risk Projection". |
| **T5** | "blood type" | **"blood group"** / "ABO blood group" | `reference_data/abo_compatibility.py:4`; `services/report_outcome_service.py:53`; `models/enums.py:9`; `compatibility_precondition_service.py:111,117` | Commonwealth usage. The frontend already says "Blood group" — the backend and the report text disagree with it. |
| **T6** | "Rh factor" | **"RhD type"** | `PatientForm.jsx:117`; `DonorForm.jsx:177`; `DetailsStep.jsx:77`; `api/patients.py:126`; `api/donors.py:137` | Dated; current lab usage is RhD / Rh(D). *(The existing tooltip explaining RhD is not a transplant criterion is correct — keep it.)* |
| **T7** | bucket label `"<3 mismatches"` | **`"1–2 mismatches"`** | `reference_data/mismatch_buckets.py:20` | 0 is also "<3". The label overlaps the bucket above it. Display label only — keep the stored value stable or migrate deliberately. |
| **T8** | "PRA" where cPRA is meant | **"cPRA"** consistently | `reference_data/pra_buckets.py`; `services/pra_bucket_service.py`; `reference_data/risk_classification.py`; wizard step label "PRA" | PRA (actual panel testing) and cPRA (calculated from unacceptable antigens + population frequencies) are different measurements. This system computes cPRA. |
| **T9** | placeholder **`"Antigen (e.g. B*44:02)"`** | **`"Antigen (e.g. B44)"`** | `pages/BeadSpecificityStep.jsx:232` | **This is defect B2.** Allele-level input cannot match and silently disables the DSA gate. |
| **T10** | `"Allele 1"` / `"Allele 2"` | `"Antigen 1"` / `"Antigen 2"` | `HlaTypingEditor.jsx:119,124` | The stored values are serological antigens, not alleles. Keep the `allele_1`/`allele_2` API fields; change the labels. |
| **T11** | "Low-Average Risk" / "High-Average Risk" | **ask the doctors** — conventional set is Low / Intermediate / High / Very High | `reference_data/risk_classification.py:44-49` | Not standard clinical risk vocabulary. See Part 5, Q5. |
| **T12** | "Too many HLA mismatches" as a rejection headline | reframe — see B1 | `constants/reportStatus.js:44`; `services/report_outcome_service.py:60` | Mismatch count alone does not make a living-donor transplant impossible. |
| **T13** | "desensitization protocol review" | "desensitisation protocol review" | `services/dsa_service.py:79` | Spelling consistency. |
| **T14** | `"DRB3,4,5"` | display as **"DRB3/4/5"** | `reference_data/hla_loci.py:14` | The comma reads as a list of three values. The frontend already displays "HLA-DRB3/4/5" — align the backend's display strings. **Do not change the enum value**; it is a stored DB value. |
| **T15** | "Pregnancy" | **"Prior pregnancy"** | `constants/clinicalEnums.js:35`; `reference_data/sensitization_weights.py:9` | It is a historical sensitising exposure, not a current state. Ask the doctors whether parity (number of pregnancies) should be captured — see Q4. |
| **T16** | "Sensitization" card implying an MFI cutoff adjustment | "Sensitising history (informational)" | `SensitizationStep.jsx`; `reference_data/sensitization_weights.py:14-18` | Reducing an MFI cutoff by a history score is not recognised clinical practice. The code already treats it as informational — the UI copy should say so plainly. |
| **T17** | "patient" and "recipient" used interchangeably | **"recipient"** in every transplant-pairing context | throughout | Standard transplant convention is recipient/donor. Keep "patient" only where the person is being discussed outside a pairing. |
| **T18** | bare "MFI" | expand on first use: "MFI (mean fluorescence intensity)" | `AntibodyProfileEditor.jsx:111` and first use per screen | |

---

## Part 4 — Phased plan

Each task names its files, its acceptance criterion, and whether it is blocked on the
doctors. **Nothing in Phase 1 depends on a clinical decision** — start there today.

---

### Phase 1 — Correctness and safety (week 1) — NOT blocked

| # | Task | Files | Done when |
|---|---|---|---|
| 1.1 | Fix B1 — incomplete typing must never read as rejection | `hla_mismatch_service.py`, `report_outcome_service.py`, `reference_data/report_outcome.py` | An all-untyped pair returns `cannot_assess` naming every missing locus; no detail string quotes imputed mismatches as measured |
| 1.2 | Fix B2 — allele-level antigen entry | `BeadSpecificityStep.jsx:232`, `schemas/antibody_profile.py`, `dsa_service.py` | Allele-level input is rejected with a clear message; **and** any antibody unmatched to a donor antigen raises a visible review flag |
| 1.3 | Fix B3 — enforce completeness at the API | `api/compatibility.py` | `POST /compatibility/check` returns 422 with `missing_inputs` when typing is incomplete; the wizard behaves unchanged |
| 1.4 | Fix B5 — report unscreened loci in the DSA step | `dsa_service.py`, `match_pipeline.py` | An anti-DQ antibody against an untyped-DQ donor produces a review flag, not silence |
| 1.5 | Pin PuLP (B11) | `pyproject.toml` | `pulp>=3.3.2,<4.0`; `uv lock` regenerated |
| 1.6 | Add `.catch()` (B6) | `NewPatientPage.jsx`, `NewDonorPage.jsx` | Duplicate NIC shows the API's message inline |
| 1.7 | Delete duplicate `/auth/me` (B7) | `main.py:118` | Route registered once; startup assertion for duplicate paths |
| 1.8 | Fix risk-tier gaps (B13) | `reference_data/risk_tiers.py`, `risk_tier_service.py` | Contiguous half-open bands; startup assertion for full coverage; boundary tests |

**Gate:** all 832 tests green plus the new ones; `ruff` and `eslint` clean.

---

### Phase 2 — Terminology (week 1–2) — NOT blocked, but needs doctor sign-off at the end

| # | Task | Done when |
|---|---|---|
| 2.1 | Apply T1–T18 (Part 3) | Every listed occurrence changed; no DB enum value, stored JSON key, or API field renamed |
| 2.2 | Normalise `-ise`/`-isation` | One spelling convention across the whole tree |
| 2.3 | Produce **`docs/clinical-copy-review.md`** | Every clinician-facing string in the app, grouped by screen, in a table with a sign-off column |
| 2.4 | **Send 2.3 to the doctors** | Their corrections applied and re-reviewed |

> **2.3 is the deliverable that answers the doctors' original comment.** Do not consider
> Phase 2 done at 2.2 — the point is to give them one document to mark up, so this
> conversation happens once instead of five times.

---

### Phase 3 — Pilot security and governance (week 2) — NOT blocked

| # | Task | Done when |
|---|---|---|
| 3.1 | TLS-terminating reverse proxy (B9) | HTTPS end to end; HSTS and security headers; HTTP redirects |
| 3.2 | Login throttling and lockout (B9) | Per-IP and per-account backoff, audited; a lockout test |
| 3.3 | Password handling (B10) | `getpass` prompt; ≥12 chars; common-password check; README updated |
| 3.4 | Purge patient-shaped identifiers (B8) | Six files use synthetic identities; CI fails on NIC-shaped literals |
| 3.5 | Session expiry warning | Doctor warned before a 60-minute expiry, with re-auth |
| 3.6 | Structured logging (B15) | JSON logs with request IDs; **no patient identifiers or antigen data in log output** |
| 3.7 | Backup and retention runbook | Documented Postgres backup, restore **tested**, retention aligned to hospital policy |

---

### Phase 4 — Maintainability and upgradability (week 2–3) — NOT blocked

| # | Task | Done when |
|---|---|---|
| 4.1 | Split unit/integration tests (B12) | `pytest app/tests/unit` runs green with no database |
| 4.2 | Migrate off deprecated PuLP APIs (B11) | Zero deprecation warnings; upper pin lifted |
| 4.3 | **Version the clinical constants** | Every reference-data module carries a version constant, stamped onto each `MatchReport`, so a report's numbers stay interpretable after a threshold changes |
| 4.4 | Single-source the duplicated constants | `sensitizationWeights.js` and `clinicalEnums.js` are hand-copied from the backend — generate them or assert equality in CI |
| 4.5 | Panel-class cross-check (B14) | A swapped-page upload is flagged, not silently mislabelled |
| 4.6 | Document the clinical-change procedure | `docs/changing-clinical-constants.md`: who approves, what to version-bump, which tests must be updated, how past reports stay interpretable |

> **4.3 and 4.6 are the "upgradable" requirement.** The doctors *will* revise these numbers.
> The system needs to absorb that without invalidating existing reports or requiring a
> developer to reason it out from scratch each time.

---

### Phase 5 — Clinical decisions (week 3–4) — **BLOCKED on the doctors**

Do not start these before the meeting. Do not guess any value.

| # | Task | Blocked on |
|---|---|---|
| 5.1 | Mismatch gate policy (B1) | Q1 |
| 5.2 | Crossmatch model (B4) | Q3 |
| 5.3 | DSA floor and band boundaries | Q2 |
| 5.4 | cPRA >60% risk points | Q6 |
| 5.5 | Risk-level label set (T11) | Q5 |
| 5.6 | Sensitising-history handling (T15, T16) | Q4 |
| 5.7 | Proposal expiry window | Q7 |
| 5.8 | One `HLA_FREQUENCY_TABLE_VERSION` bump covering every change agreed at the meeting | all of the above |

---

### Phase 6 — Pilot readiness (week 4)

| # | Task | Done when |
|---|---|---|
| 6.1 | Clean-machine deployment test | Fresh clone → README only → working system, by someone who did not write it |
| 6.2 | Backup restore drill | A real restore from backup into a clean database |
| 6.3 | Clinical acceptance test | Doctors run ~10 real anonymised pairings and confirm every verdict |
| 6.4 | Data-protection review | PDPA position documented: lawful basis, retention, access, the 20 archived lab scans |
| 6.5 | Incident and rollback plan | What happens when the system gives a wrong answer during the pilot; who is told; how it is rolled back |

---

## Part 5 — Questions for the doctors

Take these to the meeting as a single sheet. Every one blocks a Phase 5 task.

**Q1 — Should HLA mismatch count reject a pairing at all?**
The system currently rejects a pairing outright at 6/6 mismatch across A/B/DRB1
(`MAX_ACCEPTABLE_MISMATCHES = 6`). In living-donor transplantation a fully mismatched
unrelated donor — a spouse, for example — is routine and transplanted successfully; DSA
and crossmatch are what decide immunological risk. *Should mismatch count be a rejection
gate, or a risk factor that informs the verdict without blocking it?* **This is the single
most consequential clinical question in the system.**

**Q2 — DSA MFI floor and bands.** Currently: floor 1000; weak 1000–2000, moderate
2000–5000, strong ≥5000; only "strong" halts. Are these your thresholds? Should the halt
be at "strong", or should moderate DSA also stop the pipeline?

**Q3 — Crossmatch.** Should the system distinguish T-cell from B-cell, and CDC from flow
cytometry? What combination is an absolute contraindication versus a flag for review?
(Currently a single yes/no, and any positive halts.)

**Q4 — Sensitising history.** Should prior pregnancy count parity rather than yes/no?
Should the transfusion count matter? Should this history influence any threshold, or stay
purely informational as it is now?

**Q5 — Risk-level labels.** Current set: Low / Low-Average / High-Average / High. Would
Low / Intermediate / High / Very High read better in a clinical note?

**Q6 — cPRA above 60%.** No risk-score point value has been agreed for this band, so those
reports currently return "Proceed with Caution" with no risk level. What value should it
carry?

**Q7 — Proposal expiry.** Exchange proposals expire on a fixed window. Given that real
approvals take 2–4 weeks, what should it be?

**Q8 — cPRA method disclosure.** This system's cPRA is a union-probability combination over
antigen frequencies, not the haplotype-based UNOS calculation — a documented approximation
(see `hla_antigen_frequencies.py`). Are you comfortable with that method, and should the
report label the number as an estimate?

---

## Part 6 — Guardrails

**Read this before changing anything below.**

**Do not change any clinical constant without a doctor's written sign-off.** That means
`dsa_threshold.py`, `mismatch_buckets.py`, `pra_buckets.py`, `risk_classification.py`,
`risk_tiers.py`, `hla_weights.py`, `sensitization_weights.py`. Every one is on the Part 5
sheet. Changing them now means changing them twice, and the second change invalidates the
tests written for the first.

**Do not "fix" the LKDPI or Grams coefficients.** They are transcribed verbatim from the
source papers and were verified against them. If a number looks wrong, re-check the paper —
do not adjust it to taste.

**Do not remove the disclosed limitations.** The race-extrapolation disclaimer, the
"never validated in South Asian populations" notes, the cPRA independence-assumption
caveat — these are the most clinically credible thing in the codebase. A reviewer who sees
them trusts everything else more.

**Do not rename database enum values or stored JSON keys** during the terminology pass.
Display labels, docstrings, and comments only, except where Part 3 explicitly says
otherwise.

**Do not delete the legacy weighted HLA scoring path** yet. It is still computed for
comparison during the transition. Remove it once the doctors confirm the sequential
pipeline is the only one they want.

**Do not treat green tests as clinical correctness.** All 832 tests pass, and both B1 and
B2 are live. The tests encode the current behaviour; that is exactly why they did not
catch defects in what the behaviour *should* be.

---

## Appendix — Reproducing this audit

```bash
# Backend (needs PostgreSQL 16)
cd kidney-backend
TEST_DATABASE_URL="postgresql+asyncpg://postgres@127.0.0.1:5432/kidney_test" \
SECRET_KEY=test OCR_SERVICE_API_KEY=test CORS_ORIGINS="http://localhost:3000" \
  uv run pytest app/tests -q            # 502 passed
uv run ruff check .                     # All checks passed

# Frontend
cd ../kidney-frontend && npm install
npx vitest run                          # 252 passed
npx eslint .                            # clean

# OCR service
cd ../ocr-service
OCR_SERVICE_API_KEY=test uv run pytest app/tests -q   # 78 passed, 4 deselected
```

The B1 and B2 reproductions in Part 2 run from `kidney-backend/` with `PYTHONPATH=.`.
