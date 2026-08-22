# Changing a clinical constant

This is the operational procedure for changing any value in
`app/reference_data/` (locus weights, mismatch/PRA/DSA/risk-tier
boundaries, sensitisation weights, ABO compatibility, cPRA frequency
tables). For the clinical *rationale* behind each of these — what's
externally citable versus this project's own specification, and how to
safely re-derive a value if it's ever in question — see
[`clinical-basis.md`](clinical-basis.md) first. This document is the
"how to land the change" checklist; that one is the "is this number
right" reference.

## 0. Who approves

**No clinical constant changes without a doctor's written sign-off.**
Every module listed in the table below is on the open-questions sheet in
FINALIZATION-PLAN.md Part 5 — several of them (the mismatch gate, DSA
bands, risk-level labels) are waiting on a specific clinical decision, not
a code change. Get the sign-off in writing (an email, a signed copy of the
decision sheet, meeting minutes — anything durable) before touching the
file. Reference that sign-off in the PR description.

## 1. Make the change and bump the version

Every reference-data module that feeds a `MatchReport` carries a
`_VERSION` string constant (e.g. `DSA_THRESHOLD_VERSION` in
`dsa_threshold.py`). **Bump it in the same commit as the value change** —
a new suffix is enough (`"project-spec-v1"` → `"project-spec-v2"`), it
doesn't need to encode what changed. That version string, alongside every
other module's, gets stamped onto every new `MatchReport.reference_versions`
at creation time (see `app/reference_data/versions.py` and
`app/services/match_report_service.create_match_report`) — it's what lets
someone looking at an old report know which version of each table was in
force when it was generated, without diffing the full constant tables by
hand. **A value change with no version bump is a silent, invisible change**
from the point of view of every report generated before it — don't skip
this step even for what looks like a trivial adjustment.

If you're adding a brand-new reference-data module (not just changing an
existing one), also add its version constant to
`CLINICAL_REFERENCE_VERSIONS` in `app/reference_data/versions.py` and to
`EXPECTED_MODULES` in `app/tests/unit/test_reference_versions.py`.

## 2. Update the tests that encode the old value

Every module has unit tests that assert its current thresholds/weights
directly, plus at least one "worked example" test carrying a hand-computed
golden value through the whole pipeline. Both need updating, or they will
correctly fail (they're not a false alarm — they're doing their job):

| Module | Version constant | Primary test coverage |
|---|---|---|
| `abo_compatibility.py` | `ABO_COMPATIBILITY_VERSION` | `test_abo_service.py` |
| `dsa_threshold.py` | `DSA_THRESHOLD_VERSION` | `test_dsa_service.py` |
| `hla_antigen_frequencies.py` | `HLA_FREQUENCY_TABLE_VERSION` | `test_cpra_service.py` |
| `hla_weights.py` | `HLA_WEIGHTS_VERSION` | `test_hla_scoring_service.py` (carries the worked-example golden score, 6.5 — also reused by `app/tests/conftest.py`'s `COMPATIBLE_PATIENT_HLA`/`COMPATIBLE_DONOR_HLA`, so check integration tests referencing those too) |
| `mismatch_buckets.py` | `MISMATCH_BUCKETS_VERSION` | `test_hla_mismatch_service.py`, `test_report_outcome_service.py` |
| `pra_buckets.py` | `PRA_BUCKETS_VERSION` | `test_pra_bucket_service.py` |
| `risk_classification.py` | `RISK_CLASSIFICATION_VERSION` | `test_risk_classification.py` |
| `risk_tiers.py` | `RISK_TIERS_VERSION` | `test_risk_tier_service.py` (boundary tests — keep the startup assertion in `risk_tiers.py` passing: bands must stay contiguous, no gap, no overlap) |
| `sensitization_weights.py` | `SENSITIZATION_WEIGHTS_VERSION` | `test_sensitization_service.py` |

Run the fast, no-database gate first — it's the whole point of the
unit/integration test split (see `app/tests/conftest.py`'s docstring):

```bash
cd kidney-backend
uv run pytest app/tests/unit -q
```

Then the full suite (needs Postgres — see that same docstring for how to
point `TEST_DATABASE_URL` at a scratch database):

```bash
uv run pytest app/tests -q
```

## 3. Check the frontend mirror, if there is one

Two constants are hand-copied into the frontend rather than fetched from
the backend at runtime — `sensitizationWeights.js` (mirrors
`SENSITIZATION_EVENT_WEIGHTS`) and `clinicalEnums.js` (mirrors
`BloodType`/`RhFactor`/`HLALocusEnum`/`SensitizationEventTypeEnum`/`Sex`/
`Race`/`SmokingStatus` from `app/models/enums.py`). If your change touches
any of those values, update the matching frontend file in the same PR.

`scripts/check_constants_in_sync.py` (run in CI on every push/PR, see
`.github/workflows/constants-sync.yml`) fails the build if the two sides
disagree — run it locally before opening the PR:

```bash
python scripts/check_constants_in_sync.py
```

Most reference-data modules have no frontend mirror at all (the frontend
just displays whatever the backend's `MatchReport` response already
computed) — this step is a no-op for those.

## 4. Old reports stay old

Never edit a value "in place" expecting old reports to reinterpret
correctly — they can't, and shouldn't. A `MatchReport` is a snapshot: its
`reference_versions` field records what was in force when it was
generated, and fields like `DSAResult.floor`/`.bands` or
`CPRAResult.reference_table_version` go further and embed the actual
numbers used, not just a version label. Changing `RISK_TIERS` next month
must never change what a report generated today says — that's the entire
point of the versioning in step 1. If you ever find yourself wanting to
"backfill" old reports with recalculated values after a constant change,
stop — that has already gone wrong once (see the deliberate frozen-copy
backfill in migration `7a8b6052701d`, which recomputes from *already-
stored* step results using a copy of the decision table frozen at
migration time, specifically so a later change to the live logic can't
retroactively reinterpret it).

## 5. What NOT to do

- Don't change a value without a version bump (step 1).
- Don't change `donor_risk_model.py` or `lkdpi_model.py` — those are
  transcribed verbatim from their source papers (Grams et al. NEJM 2016;
  Massie et al. AJT 2016) and are deliberately excluded from
  `CLINICAL_REFERENCE_VERSIONS` (see that module's docstring). If a number
  in either one looks wrong, re-check the paper; don't adjust it to taste.
- Don't rename a stored JSON key, a database enum value, or a bucket's
  internal `name` (e.g. `mismatch_buckets.py`'s `"<3 mismatches"`, kept
  stable specifically because it's a lookup key and a persisted value —
  see that file's own comment) as part of a value change. Change the
  *display label* instead; the two are deliberately decoupled.
