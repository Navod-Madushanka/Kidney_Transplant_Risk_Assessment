# Implementation prompt — Part E: make LKDPI actually run

**Insert as Part E of `implementation-prompt.md`, after Part D (LKDPI).** Part D shipped correctly.
This part fixes the reason none of it produces a number. Everything below the line goes to your
coding agent.

---

## E0. Diagnosis — read this before touching anything

Part D is **complete and working**. `lkdpi_model.py`, `lkdpi_service.py`, the call in
`run_match_pipeline`, the JSONB column, `max_lkdpi_quality`, and `LKDPIScoreCard` in
`ReportDetailPage.jsx` all exist and behave as specified.

The score never appears because **the wizard feeds it an empty record**.
`buildPersonPayload()` in `src/api/compatibilityWizard.js` sends exactly five fields:

```js
{ full_name, date_of_birth, blood_type, rh_factor, nic_number, details_verified }
```

`ReviewStep` then calls `createPatient()` / `createDonor()` with that payload, so every check
creates a brand-new patient and donor with every clinical column `NULL`. Running the real service
against exactly that shape:

```
has_sufficient_data: False   score: None
missing (10): donor eGFR, donor BMI, donor race, donor smoking status, donor systolic BP,
donor sex, recipient sex, donor biological relationship to recipient, donor weight,
recipient weight
```

`LKDPIScoreCard` therefore renders its insufficient-data branch on every report, forever. The
service is behaving exactly as D3.1 specifies — it is refusing to guess. Nothing in
`lkdpi_service.py` is wrong.

The same blank records also starve the Grams donor-safety assessment, which needs eGFR, BMI, SBP,
DBP, race, smoking status, diabetes, urine ACR and antihypertensive use — none of which the wizard
collects either.

### Why "add an LKDPI step" is the wrong fix

LKDPI has **no inputs of its own**. All 13 terms are either clinical facts the system already
models on `donors`/`patients`, or values the pipeline derives (`abo_result.is_compatible`,
`mismatch_result.locus_breakdown`). A step named after a score models the score rather than the
clinical workflow, and you would immediately need a second one for Grams. `PatientForm.jsx` and
`DonorForm.jsx` **already collect every one of these fields**. Adding a wizard step duplicates that
entry surface and leaves two places to keep in sync.

### The real defect underneath

Creating a fresh patient and donor on every check is a bug in its own right, independent of LKDPI:

- `ix_donors_nic_number_active_unique` (migration `b2d4f6a8c0e3`) makes `donors.nic_number`
  **globally unique across all active rows**; patients are unique per doctor. So the **second**
  compatibility check on the same real pair returns `409 You already have a patient with this NIC
  number.` The wizard cannot re-check a pairing.
- Every check silently forks a new clinical record for a person who already exists, so the patient
  detail page, donor search pool and exchange pool all fill with duplicates.
- `NewCheckFromRecordsPage.jsx` already asks the doctor to pick an existing patient and donor —
  then throws both IDs away and uses them only to pre-fill photos.

Fix the linking and the LKDPI inputs arrive for free, because the records the doctor selects were
created through `PatientForm`/`DonorForm`, which collect everything.

---

## E1. The change in one sentence

**The wizard stops creating people and starts running a check on two records that already exist.**

Delivered in three phases. Phase 1 alone makes LKDPI produce numbers.

| Phase | Scope | Unblocks |
|---|---|---|
| 1 | Subject selection + linked writes + readiness panel | LKDPI and Grams both start scoring |
| 2 | OCR reconciliation on `DetailsStep` | OCR can update a linked record safely |
| 3 | Retire create-on-submit entirely | Kills the 409 and the duplicate records |

---

## E2. Backend changes

Small. **No migration is needed** — every column already exists, and `PUT /patients/{id}` and
`PUT /donors/{id}` already accept every LKDPI and Grams field.

### E2.1 `details_verified` must be settable on update

`PatientUpdate` and `DonorUpdate` have no `details_verified` field, so it can only be set at
creation. Once the wizard writes to an *existing* record, an OCR extraction that overwrites a
linked patient's name or DOB has no way to mark those details unconfirmed — and
`POST /compatibility/check` would keep running on them.

Add to both schemas, with the exact `None` = "no claim being made" contract already documented on
`hla_typing_service._resolve_verified`:

```python
details_verified: bool | None = None
```

Plumb it through `update_patient_details` / `update_donor_details` using `_resolve_verified`, not a
bare assignment — an omitted field must preserve the current value, never reset it to `True`. Reuse
the existing helper; do not write a second copy of that logic.

### E2.2 Sensitization events must become idempotent

`create_sensitization_events` appends unconditionally, and
`calculate_sensitization_score` sums **every** row returned by
`get_patient_sensitization_event_types`. Today that is harmless because each check gets a fresh
patient. The moment the wizard writes to a linked patient, re-running a check re-adds the same
events and the sensitization score doubles, then triples.

Add `PUT /patients/{patient_id}/sensitization-events` with replace semantics, mirroring the
existing `PUT .../hla-typings` and `PUT .../antibody-profiles` exactly (delete-then-insert in one
transaction, audit log with `previous_count`/`new_count`). The wizard's sensitization step is three
booleans — an inherently complete statement of the current set, so replace is the correct verb.

**Keep `POST` as-is** for the patient detail page's "add one event" flow. Point the wizard at the
new `PUT`.

### E2.3 New endpoint — `GET /compatibility/readiness`

This is what replaces "a new step for the doctor to input values". One endpoint, one source of
truth, no clinical rules duplicated in the frontend.

```
GET /compatibility/readiness?patient_id=<uuid>&donor_id=<uuid>
```

Resolve both records with the **same** functions `POST /compatibility/check` uses
(`get_patient_by_id_for_doctor`, `get_donor_for_compatibility_check`) so the two endpoints can
never disagree about visibility. 404 identically.

```python
@dataclass
class ReadinessGap:
    code: str          # "patient_hla_typing" | "donor_weight" | ...
    label: str         # doctor-facing, reuse lkdpi_service.FIELD_LABELS wording
    subject: str       # "patient" | "donor"

@dataclass
class CompatibilityReadiness:
    can_run: bool
    blocking: list[ReadinessGap]           # POST /check would 422 or halt on data absence
    lkdpi_gaps: list[ReadinessGap]         # score withheld
    donor_risk_projection_gaps: list[ReadinessGap]
    donor_risk_contraindication_gaps: list[ReadinessGap]
```

Build it by **calling the existing services**, never by re-deriving:

| Output | Source |
|---|---|
| `blocking` — unverified OCR | the same five `*_verified` checks in `app/api/compatibility.py`, extracted into a shared helper both endpoints call |
| `blocking` — missing A/B/DRB1 | `calculate_mismatch_result(...).missing_inputs` |
| `lkdpi_gaps` | `calculate_lkdpi(...).missing_inputs` |
| `donor_risk_projection_gaps` | `assess_donor_risk(...).missing_projection_predictors` |
| `donor_risk_contraindication_gaps` | `assess_donor_risk(...).missing_contraindication_predictors` |

Extract the verification block in `check_compatibility` (lines 52–72) into
`app/services/compatibility_precondition_service.py` and have **both** endpoints call it. Two
copies of that list will drift within a month.

Note the deliberate asymmetry: missing HLA typing is **blocking**, missing LKDPI inputs are **not**.
A doctor with no eGFR result yet must still be able to run ABO / HLA / DSA / crossmatch. The score
is withheld; the check runs.

---

## E3. Frontend — wizard state

### E3.1 New `subject` block

In `buildInitialWizardState()` (`src/context/wizardReducer.js`):

```js
subject: {
  mode: "select",        // "select" | "create"
  patientId: null,
  donorId: null,
  readiness: null,       // last GET /compatibility/readiness response
},
```

New actions: `SET_SUBJECT`, `SET_READINESS`. Expose `setSubject` / `setReadiness` on
`WizardProvider`'s `actions` memo.

### E3.2 `patient_details` / `donor_details` stay demographic

Do **not** widen these into the full clinical panel. They exist to hold what OCR reads off a
document, and OCR reads names, DOBs and blood types — not eGFR. Clinical data comes from the linked
record, entered through `PatientForm`/`DonorForm`. Keeping that boundary is the whole point of this
part.

### E3.3 New first step — `SubjectStep`

Insert at the head of `WIZARD_STEPS` in `src/constants/wizardSteps.js`:

```js
{ key: "subject", label: "Patient & Donor", path: "subject" },
```

…and relabel the existing `details` step to `"Confirm details"`. Add the route in `App.jsx` and
change the wizard's `index` redirect from `photos` to `subject`.

The step offers two `Select` dropdowns over `listPatients()` / `listDonors()` — the same query
`NewCheckFromRecordsPage` already runs — plus a "Register a new patient / donor" link that routes
to `/patients/new` and `/donors/new` and returns. Reuse the existing forms; do not inline a copy.

On both IDs set, fetch `GET /compatibility/readiness` and render:

- **Blocking gaps** — red, and `Continue` is disabled. Each row deep-links to the field that fixes it.
- **Score gaps** — amber, informational, `Continue` stays enabled. Copy along the lines of:
  *"LKDPI will not be calculated — donor weight and recipient weight are missing on these records.
  The check itself will run normally."* Each row links to `/donors/:id` or `/patients/:id`.
- **No gaps** — a single green "Ready to check" line.

This panel is the answer to "should there be a step where the doctor inputs values": it is empty
when the records are complete, and it names exactly the missing fields in the service's own
wording. A fixed step can never be empty.

### E3.4 `NewCheckFromRecordsPage` passes the IDs

It already selects the pair. Change one line — carry the IDs through alongside the photos:

```js
navigate("/checks/new/subject", { state: { prefillPhotos, patientId, donorId } })
```

Read them in `WizardProvider`'s lazy-init the same way `prefillPhotos` is read today, seeding
`subject`. The page's own copy still stands; it just stops discarding half its output.

### E3.5 `submitCompatibilityCheck` writes to the linked records

In `src/api/compatibilityWizard.js`, replace the create calls:

```js
// before
if (!next.patientId) { const p = await createPatient(buildPersonPayload(...)); ... }

// after
next.patientId ??= wizardState.subject.patientId
next.donorId   ??= wizardState.subject.donorId
if (!next.patientDetailsDone) {
  await updatePatient(next.patientId, buildPersonPayload(wizardState.patient_details, detailsOcrVerified))
  await completeStep({ patientDetailsDone: true })
}
```

`updatePatient` / `updateDonor` already exist in `src/api/patients.js` / `donors.js`. Everything
downstream — HLA typings, antibody profiles, the compatibility check itself — is unchanged, because
it was already keyed on `patientId`/`donorId`.

Point the sensitization call at the new `PUT` from E2.2.

Update `SUBMISSION_STEPS` in `ReviewStep.jsx`: *"Creating patient record"* → *"Updating patient
record"*. The resume-on-failure logic keeps working unchanged; that design already anticipated this.

### E3.6 Blood type is immutable — surface the conflict

`PatientUpdate` / `DonorUpdate` deliberately exclude `blood_type` and `rh_factor`. If OCR reads a
blood type off today's document that disagrees with the linked record, the wizard must **say so**,
not silently drop it. On `DetailsStep`, when
`wizardState.patient_details.blood_type !== linkedPatient.blood_type`, block `Continue` with:

> *"This document reads blood group B+, but this patient's record says A+. One of them is wrong.
> Blood group is permanent once set — resolve this before running the check."*

Silently discarding a mismatched blood type on the ABO gate's own input is the worst available
failure mode here.

---

## E4. Phase 2 — `DetailsStep` becomes reconciliation

Once the subject is linked, `DetailsStep` is no longer a blank form. Render three columns per
field: **On record** · **Read from document** · **Use**. Default to the record's value; the doctor
opts in to each OCR overwrite. Only changed fields go into the `PUT`.

This also fixes something Part A left open: `HYDRATE_FROM_OCR` currently overwrites
`patient_details` whenever OCR finds a truthy value, with the record's own value nowhere in view.
Against a linked record that is a silent overwrite of stored clinical data.

---

## E5. Phase 3 — retire create-on-submit

Delete the `createPatient` / `createDonor` calls from `compatibilityWizard.js` entirely and make
`subject.mode === "select"` the only path. Registration happens on `/patients/new` and
`/donors/new`, which already validate properly. This is what removes the 409 and stops the
duplicate-record accumulation.

---

## E6. Effect on the scoring system: none, and prove it

The verdict must not move. `build_report_outcome()` does not take `lkdpi_result` today and must not
start. Three independent axes:

| Layer | Question | Source |
|---|---|---|
| Verdict | Can this go ahead? | `report_outcome.py` — hard gates only |
| `final_risk_level` | How immunologically risky? | `risk_classification.py` — mismatch + cPRA |
| LKDPI | How good is the graft, if it proceeds? | `lkdpi_service.py` — display + ranking only |

Two reasons beyond the ones already in `scoringsystemrecommendation.md`:

1. LKDPI's external C-statistic is **0.55**. Letting a near-chance discriminator into a gate lets it
   override ABO and crossmatch — hard biological facts — by proxy.
2. LKDPI already contains `8.57 × hla_b_mismatches + 8.26 × hla_dr_mismatches`, and Steps 3 and 7
   score those same mismatches. Feeding LKDPI back into the verdict double-counts them.

**Make this a test, not a comment.** In `app/tests/integration/test_compatibility.py`:

> Run the identical pairing twice — once with the four LKDPI fields populated, once with them
> `NULL`. Assert `overall_status`, `outcome.verdict`, `outcome.review_flags` and `final_risk_level`
> are byte-identical across both runs, and that only `lkdpi_result` differs.

That is the guard rail. Without it, "keep them separate" is a docstring that survives until the
first person who thinks a score should affect the verdict.

Where LKDPI *does* legitimately change behaviour, both already built and both correct:
`max_lkdpi_quality` in `exchange_matching_service.py`, and `lkdpi_score`/`lkdpi_band` on the
dashboard summary schemas for sorting.

---

## E7. Fix these in the same pass

### E7.1 `single_factor_override` fires on every healthy donor — **blocking**

`lkdpi_service.py:257` compares raw contributions (coefficient × absolute value) against a fixed
25.0. The continuous terms are large by construction, so the callout is permanently on. A textbook
ideal donor (age 35, eGFR 100, BMI 23, SBP 118, never-smoker, related, 0/0 mismatches, ratio 0.86)
scores **−14.17, band `excellent`** — and still gets:

```
OVERRIDE: {'label': 'Donor systolic BP (118.0 mmHg)', 'points': 51.92}
```

eGFR (−38.10), weight ratio (−43.60) and BMI (+26.91) all clear the threshold on that same donor.
Ship this as-is and the NEWS2 override in `reportmockup.html` cries wolf on 100% of reports, which
is worse than not having it — it trains the reader to skip the one element the card exists to make
them read.

**Fix.** Add a reference case to `lkdpi_model.py` and flag *deviation from it*, not absolute
magnitude:

```python
# Median US living donor from Massie 2016's derivation cohort, used ONLY as the
# baseline the single-factor override measures deviation against. Not a default,
# never substituted for a missing input -- see lkdpi_service._missing_fields.
REFERENCE_CASE = LKDPIReferenceCase(
    donor_age_years=45, donor_egfr=95.0, donor_bmi=26.0, donor_systolic_bp=120.0,
    weight_ratio=0.9, hla_b_mismatches=1, hla_dr_mismatches=1,
    donor_african_american=False, donor_ever_smoked=False,
    both_male=False, abo_incompatible=False, biologically_unrelated=False,
)
SINGLE_FACTOR_OVERRIDE_THRESHOLD = 15.0
```

Then `delta = term_points − reference_term_points`, and the override fires on
`abs(delta) > SINGLE_FACTOR_OVERRIDE_THRESHOLD`. SBP 118 gives `0.44 × (118 − 120) = −0.88` — no
override, correctly. SBP 160 gives `+17.6` — override, correctly.

Keep raw `points` in `contributions` (the bars are a decomposition of the score and must still sum
to it); carry `delta` as an additional key. Both the threshold and the reference case are project
conventions, not clinical policy — add a row for each to `docs/clinical-basis.md` §7 alongside the
band boundaries already labelled that way.

### E7.2 The intercept is missing from `contributions`

`reportmockup.html` renders `{n:"Model intercept", p:-11.30}` as a component bar.
`lkdpi_service.py:244` adds `COEFFICIENTS.intercept` outside the `terms` list, so it never reaches
`contributions` and the bars do not sum to the score. Pick one and make the test assert it:

- **(a)** Add the intercept as a term. Bars sum exactly to `score`. Must be excluded from the
  override scan — an intercept is not a clinical driver.
- **(b)** Keep it out and label the bar block *"What moved this score from the baseline"*, matching
  D7's stated invariant (*contributions sums to score minus the intercept*).

**(b)** is more honest and matches the existing test. Update the mockup, not the service.

### E7.3 Duplicate LKDPI input adapters

`match_pipeline._build_lkdpi_input` and `exchange_graph_service._edge_lkdpi` build the same
`LKDPIInput` from the same ORM columns. The existing comment justifies the duplication by the
`abo_result` difference, but that is one field. Extract
`lkdpi_input_from_records(donor, patient, mismatch_result, *, abo_incompatible)` into
`lkdpi_service.py`. Two adapters over 14 clinical fields will drift.

### E7.4 Get Part D into git

`app/reference_data/lkdpi_model.py`, `app/reference_data/report_outcome.py`,
`app/services/lkdpi_service.py`, `app/services/report_outcome_service.py`, migrations
`7a8b6052701d` and `b8c91b0b56bd`, and three test files are all **untracked**. A fresh clone cannot
import `app.main`. Commit them before anything else in this part.

---

## E8. Tests

**Backend**

- `test_compatibility_readiness.py` — complete pair returns `can_run=True` and all gap lists empty;
  a donor missing `weight_kg` returns `can_run=True` with `"donor weight"` in `lkdpi_gaps` and
  nothing in `blocking`; an unverified-OCR patient returns `can_run=False`; readiness and
  `POST /check` agree on every 404 case.
- `test_patients.py` / `test_donors.py` — `PUT` with `details_verified` omitted preserves the
  current value (both when currently `True` and when currently `False`); explicit `False` sets it.
- `test_patients.py` — `PUT .../sensitization-events` twice with the same body leaves exactly one
  row per event type, and the resulting `sensitization_result.total_score` is identical across both
  runs. This is the regression test for the doubling bug.
- `test_compatibility.py` — the verdict-invariance test from E6.
- `test_lkdpi_service.py` — the ideal donor from E7.1 produces `single_factor_override is None`;
  SBP 160 with everything else at reference produces an override naming systolic BP; `contributions`
  still sums to `score − intercept`.

**Frontend**

- `SubjectStep.test.jsx` — blocking gap disables Continue; a score-only gap does not; the ready
  state shows neither panel.
- `compatibilityWizard.test.js` — submission calls `updatePatient`/`updateDonor`, never
  `createPatient`/`createDonor`; resume-after-failure skips already-completed steps unchanged.
- `DetailsStep.test.jsx` — a blood-type conflict between the document and the record blocks Continue
  and names both values.

---

## E9. Do not

- **Do not add an "LKDPI step."** The score has no inputs of its own. If a field genuinely needs a
  new home, it belongs on `PatientForm`/`DonorForm` with everything else about that person.
- **Do not let LKDPI touch the verdict.** Not as a gate, not as a tiebreak, not as a review flag —
  not without the doctors asking for it in writing first. E6's test enforces this.
- **Do not widen `patient_details`/`donor_details` into a clinical panel.** That reopens the
  two-entry-surfaces problem this part exists to close.
- **Do not substitute a default for a missing LKDPI input** to make the card render. The refusal is
  the feature; `REFERENCE_CASE` in E7.1 is for the override comparison only and must never be read
  by `_missing_fields` or by any term computation.
- **Do not silently drop a blood-type mismatch** between an OCR read and a linked record. See E3.6.
