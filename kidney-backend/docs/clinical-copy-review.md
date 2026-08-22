# Clinical copy review

Every clinician-facing string changed in the Phase 2 terminology pass (FINALIZATION-PLAN.md
Part 3, glossary items T1-T18, T11 excluded — blocked on the doctors' meeting, see Part 5 Q5).
Grouped by screen/surface. **Sign-off** is blank for the doctors to mark up; nothing here should
be treated as final until that column is filled in.

No database enum value, stored JSON key, or API field was renamed as part of this pass — only
display labels, docstrings, comments, and free-text messages changed. Where a value is genuinely
a stored/lookup key (e.g. HLA mismatch bucket names, `pra_bucket_result`), the stored value is
listed unchanged and a separate *display label* translation was added instead — noted per row.

---

## 1. Risk labels

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 1.1 | Risk tier ("Highest" band) — legacy comparison score, report detail page, `Badge` fallback | "High Genetic Risk" | "High Immunological Risk" | T1 (materially wrong — reads as a heritable-disease screen) | |

## 2. Blood group / RhD

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 2.1 | New patient / New donor / Confirm details (wizard) | "Rh factor" (field label + required-field error) | "RhD type" | T6 | |
| 2.2 | Donor search results table (column header + tooltip) | "Rh factor" / "Rh factor is not a kidney transplant compatibility criterion…" | "RhD type" / "RhD type is not a kidney transplant compatibility criterion…" | T6 | |
| 2.3 | Donor search results table (column header) | "Blood type" | "Blood group" | T5 | |
| 2.4 | ABO-fail report headline (Step 1 detail) | "Recipient blood type X is not compatible with donor type Y." | "Recipient blood group X is not compatible with donor blood group Y." | T5 | |
| 2.5 | Report detail page, Step 1 row label | "Recipient / donor blood type" | "Recipient / donor blood group" | T5 | |
| 2.6 | Exchange cycle graph, edge tooltip | "Recipient blood type … Donor blood type …" | "Recipient blood group … Donor blood group …" | T5 | |
| 2.7 | Confirm details (wizard), OCR-conflict warning | "…blood type is permanent once set on a record." | "…blood group is permanent once set on a record." | T5 | |
| 2.8 | `POST /compatibility/check` 422 / readiness panel gap text | "…demographic details (name/DOB/blood type)" | "…demographic details (name/DOB/blood group)" | T5 | |
| 2.9 | `PUT /patients/{id}`, `PUT /donors/{id}` docstrings | "Blood type and Rh factor are permanent…" | "Blood group and RhD type are permanent…" | T5, T6 | |

## 3. HLA typing wizard

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 3.1 | HLA typing entry (both the reusable editor and the wizard step, patient + donor sides) | "Allele 1" / "Allele 2" | "Antigen 1" / "Antigen 2" | T10 (stored values are serological antigens, not alleles; `allele_1`/`allele_2` API fields unchanged) | |
| 3.2 | HLA locus list, any server-built message naming a locus | "DRB3,4,5" | "DRB3/4/5" (display only — `HLALocusEnum` value unchanged; frontend already did this) | T14 | |

## 4. Antibody / bead-specificity entry

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 4.1 | Bead specificity step, antigen field placeholder | "Antigen (e.g. B\*44:02)" | "Antigen (e.g. B44)" | T9 — **this was defect B2**, fixed prior to this pass; listed for completeness | |
| 4.2 | Antibody profile editor (patient detail page), subtitle | "…MFI values feed the DSA check" | "…MFI (mean fluorescence intensity) values feed the DSA check" | T18 | |
| 4.3 | Bead specificity step, intro paragraph | "…and its MFI value from the bead chart…" | "…and its MFI (mean fluorescence intensity) value from the bead chart…" | T18 | |

## 5. Sensitising-history wizard step (formerly "Sensitization")

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 5.1 | Wizard step nav label | "Sensitization" | "Sensitisation" | T3 (spelling) | |
| 5.2 | Step heading | "Sensitization" | "Sensitising history (informational)" | T16 — reframes the card as informational, matches the body copy already there | |
| 5.3 | Event list card title | "Sensitizing events" | "Sensitising events" | T3 | |
| 5.4 | Event option label | "Pregnancy" | "Prior pregnancy" | T15 (historical exposure, not a current state) | |
| 5.5 | Score readout | "Sensitization score: X pts" / "+X sensitization points" | "Sensitisation score: X pts" / "+X sensitisation points" | T3 | |
| 5.6 | Review & submit step, summary card | title "Sensitization" | "Sensitisation" | T3 | |
| 5.7 | Review & submit step, progress list | "Saving sensitization events" | "Saving sensitisation events" | T3 | |
| 5.8 | Review & submit step, validation error | "…go back to Sensitization to fill these in." | "…go back to Sensitisation to fill these in." | T3 | |
| 5.9 | Patient detail page, event editor card | title "Sensitization events", subtitle "…pregnancy…sensitization score", empty state "No sensitization events recorded yet." | "Sensitisation events" / "…prior pregnancy…sensitisation score" / "No sensitisation events recorded yet." | T3, T15 | |
| 5.10 | Report detail page, Step 2 | "Step 2 — Sensitization" (×2), "Total sensitization score" | "Step 2 — Sensitisation", "Total sensitisation score" | T3 | |
| 5.11 | New patient/donor pairing step, info text (×2) | "…sensitization events…" | "…sensitisation events…" | T3 | |

## 6. DSA / desensitisation

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 6.1 | DSA strong-match warning (report detail, audit trail) | "Patient has a {severity} antibody against donor HLA…" | "Recipient has a {severity} antibody against donor HLA…" | T17 | |
| 6.2 | DSA weak/moderate-match message | "…flagged for desensitization protocol review." | "…flagged for desensitisation protocol review." | T13 | |
| 6.3 | Report detail page, Step 5 summary | "Weak/moderate DSA — flagged for desensitization review" / "No donor-specific antibody above the MFI floor" | "…desensitisation review" / "…MFI (mean fluorescence intensity) floor" | T3, T18 | |
| 6.4 | Exchange cycle graph, edge label + tooltip (×2) | "Needs desensitization review (DSA)" / "DSA: requires desensitization-protocol review" | "…desensitisation review…" / "…desensitisation-protocol review" | T3 | |
| 6.5 | Exchange pool page, hard-to-match hint | "…the sensitization signal. Consider desensitization or national referral." | "…the sensitisation signal. Consider desensitisation or national referral." | T3 | |
| 6.6 | Exchange pool page, hard-to-match worklist description | "…the desensitization / national-referral worklist." | "…the desensitisation / national-referral worklist." | T3 | |
| 6.7 | Positive-crossmatch report detail | "The patient's serum reacted against donor cells on crossmatch…" | "The recipient's serum reacted…" | T17 | |

## 7. HLA mismatch count (Step 3)

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 7.1 | Mismatch bucket display, wherever `bucket_name` is shown (report detail Step 3 summary, donor search results column) | "<3 mismatches" shown verbatim | "1-2 mismatches" (display label only — the stored bucket name and its use as a `risk_classification.py` lookup key are unchanged) | T7 | |
| 7.2 | Rejection headline, halted-mismatch report | "Too many HLA mismatches" | "HLA mismatch count above this system's configured threshold" | T12 — **wording only**, the reject gate itself (`MAX_ACCEPTABLE_MISMATCHES = 6`) is unchanged pending Q1 | |

## 8. cPRA (Step 4)

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 8.1 | Report detail page, Step 4 name (×2) and combined-score row label | "Step 4 — PRA" / "…Step 4 PRA bucket" | "Step 4 — cPRA" / "…Step 4 cPRA bucket" | T8 | |

## 9. Donor safety assessment (Grams model)

| # | Screen | Was | Now | Ref | Sign-off |
|---|---|---|---|---|---|
| 9.1 | Module/docstring framing only — no user-visible string currently says "ESRD" (frontend already said "kidney failure risk") | "ESRD risk projection" | "kidney-failure risk projection" | T4 (KDIGO 2020 consensus nomenclature) — the model, coefficients, and citation text are unchanged | |

---

## Not changed in this pass

- **T11** (risk-level label set: "Low-Average"/"High-Average" → Low/Intermediate/High/Very High) —
  explicitly blocked on the doctors (Part 5, Q5). Do not guess.
- **T12**'s underlying question (should mismatch count reject a pairing at all) — blocked on Q1.
  Only the headline wording changed here; the gate is untouched.
- **T17** (patient vs. recipient, "throughout") — applied only to the clearest pairing-context
  clinical messages listed in §6 above (DSA warning, crossmatch detail). The much larger sweep
  the plan describes ("recipient" in every transplant-pairing context, everywhere) was judged out
  of scope for a single pass — "patient" is also the correct word in every non-pairing context
  (the `Patient` entity itself, `/patients` routes, patient-detail screens), and a blanket find/
  replace risked touching those. Flagging for a follow-up pass focused specifically on
  pairing-context report/UI copy if the doctors want it carried further.
- **-ise/-isation spelling**: normalized wherever the word appears in clinician-facing text,
  docstrings, and comments for `sensitis(ed/ation)`, `desensitisation`, and `normalised` in its
  antigen-data-processing sense. Generic programming vocabulary (`initialize`, `serialize`,
  `authorize`, `organize`, `optimize`, `denormalized` as a DB term) was deliberately left in its
  existing spelling — not clinical terminology, and rewriting it would just be code churn.

## Guardrails observed

- No stored JSON key, DB enum value, or API field was renamed. Two internal-only Python
  identifiers were renamed since neither is serialized or part of any wire format:
  `sensitized_antigens` → `unacceptable_antigens` (T2, parameters/locals throughout
  `cpra_service.py`, `match_pipeline.py`, `exchange_matching_service.py`, and the
  `get_patient_sensitized_antigens` → `get_patient_unacceptable_antigens` function), and
  `PRA_BUCKET_POINTS`/`pra_bucket_name` → `CPRA_BUCKET_POINTS`/`cpra_bucket_name` in
  `risk_classification.py` (T8, called positionally everywhere, so nothing broke).
- No clinical constant (threshold, weight, band boundary, coefficient) changed value. The
  mismatch-bucket and HLA-locus display-label maps introduced for T7/T14 are additive lookups
  layered on top of the existing stored values, not replacements for them.
- The Alembic migration `7a8b6052701d_add_outcome_to_match_reports.py` duplicates
  `report_outcome_service.py`'s headline/detail text (by design — it runs with no app imports,
  see its own module docstring) and was updated in lockstep with §2.4, §7.1, §7.2, and §6.7 above
  so `test_outcome_migration_backfill.py`'s live-vs-migration comparison stays green. This is the
  one migration file touched; no other already-applied migration was edited.

## Verification

- Backend: 524 tests passing, `ruff check .` clean.
- Frontend: 258 tests passing (test assertions updated alongside every string change above that
  had a matching test), `eslint .` clean.
