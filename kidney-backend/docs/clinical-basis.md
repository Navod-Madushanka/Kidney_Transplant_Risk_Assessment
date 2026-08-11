# Clinical basis for this system's scoring

This is the single place that documents *why* every clinical/scoring constant in this codebase
has the value it has, and where that value actually came from. It replaces three scattered
one-line comments (`hla_weights.py`: "slide 7 and slide 8", `sensitization_weights.py`: "slide
5", `risk_tiers.py`: "slide 10") that pointed at a slide deck with no further explanation
reachable from the code itself — useful to whoever wrote them, meaningless to anyone else
reading the source cold.

Two genuinely different kinds of "clinical basis" are mixed together in this app, and this doc
is honest about which is which:

1. **Externally published, independently verifiable** — the donor safety-assessment model and
   the cPRA antigen-frequency table. Both cite a real paper with a DOI, and both document their
   own methodology and limitations in-repo (see their reference-data modules directly — this doc
   doesn't duplicate that, it points to it).
2. **Project-specification values** — the HLA locus mismatch weights, sensitization event
   weights, and risk-tier boundaries below. These come from this project's own clinical
   specification (the "slide N" the code comments reference), not from an external publication
   this codebase can cite by DOI. That specification isn't part of this repository, so this doc
   records the values, their role in the pipeline, and their provenance as accurately as the
   code itself can — it does not fabricate a literature citation for numbers that were assigned
   by the project spec, not derived from one.

---

## 1. HLA locus mismatch weights (`app/reference_data/hla_weights.py`)

Used by the older weighted `hla_scoring_service.py` path (all 9 HLA loci, weighted by
immunogenic significance) — distinct from Step 3 of the sequential pipeline
(`hla_mismatch_service.py`), which only counts A/B/DRB1 unweighted (see §3 below). Both paths
exist in this codebase; this table only feeds the weighted one.

| Locus | Weight | Tier |
|---|---|---|
| DRB1 | 1.50 | Highest — DR mismatches are the strongest independent predictor of rejection risk among HLA loci in the transplant literature this project's specification was built from. |
| B | 1.00 | High |
| A, C, DQB1 | 0.50 | Moderate |
| DRB3,4,5, DQA1, DPA1, DPB1 | 0.25 | Lowest — loci with comparatively weaker or less-established immunogenic significance, and (for DRB3,4,5) not universally expressed. |

**Provenance**: project specification slides 7 (tier definitions) and 8 (full locus list, worked
example). The *relative* ordering (DRB1 > B > A/C/DQB1 > the rest) is consistent with the
general clinical understanding that DR mismatches matter most, followed by B, which is why this
doc doesn't flag the ordering itself as suspect — only the fact that the exact numeric weights
(1.50/1.00/0.50/0.25) have no external citation reachable from this codebase.

## 2. Sensitization event weights (`app/reference_data/sensitization_weights.py`)

| Event | Weight |
|---|---|
| Previous transplant | 2.0 |
| Pregnancy | 1.0 |
| Blood transfusion | 0.5 |

Feeds `SensitizationResult.adjusted_mfi_cutoff` — **informational/reference display only** on
the report's Step 2 card, not an input to any real accept/reject gate. Step 5's DSA check has
its own independent, published-threshold-adjacent severity bands (`dsa_threshold.py`, see §4)
that this factor does not adjust. The relative ordering (prior transplant sensitizes a recipient
more than pregnancy, which sensitizes more than transfusion) matches standard clinical teaching
on sensitizing events; the specific weights (2.0/1.0/0.5) are project-specification slide 5.

## 3. HLA mismatch buckets (`app/reference_data/mismatch_buckets.py`)

Step 3 of the sequential pipeline counts mismatches at **A, B, and DRB1 only** (unweighted, 0-6
possible) — a narrower, unweighted alternative to §1's weighted 9-locus score, per the current
project specification (not the same spec revision §1 came from — see that module's docstring for
why the two coexist).

| Bucket | Range |
|---|---|
| 0 mismatches | 0 |
| <3 mismatches | 1-2 |
| 3-6 mismatches | 3-6 (reject) |

`MAX_ACCEPTABLE_MISMATCHES = 6` is also the maximum value three loci × two alleles can ever
reach — the gate is `>= 6`, not `> 6`, precisely because a strict "reject only above the
maximum reachable value" rule could never fire (see the module's own comment; this was a real
bug, fixed 2026-08-08).

## 4. DSA (donor-specific antibody) severity bands (`app/reference_data/dsa_threshold.py`)

| Band | MFI range | Pipeline effect |
|---|---|---|
| (below floor) | < 1000 | Not flagged as a DSA at all |
| Weak | 1000 – 1999 | `requires_review`, does not halt |
| Moderate | 2000 – 4999 | `requires_review`, does not halt |
| Strong | ≥ 5000 | Halts the pipeline outright |

This is the one locally-derived threshold system with genuine external grounding beyond a slide
number: MFI-graded severity bands (rather than a single flat cutoff) reflect standard clinical
DSA interpretation practice — single-antigen-bead MFI is a continuous, semi-quantitative signal,
and treating everything above one flat number as an equally hard reject (this codebase's
previous behavior, `DSA_MFI_THRESHOLD = 1000`, fixed 2026-08-08) both over-rejected weak/
equivocal antibodies and, more importantly, was clinically wrong about the shape of the risk. See
the module's own docstring for the full before/after reasoning; nothing further to add here.

## 5. cPRA / HLA antigen frequencies (`app/reference_data/hla_antigen_frequencies.py`)

**Externally published, independently verifiable — no changes needed here, referenced for
completeness.** Source: Grifoni A, Weiskopf D, Lindestam Arlehamn CS, et al. "Sequence-based
HLA-A, B, C, DP, DQ, and DR typing of 714 adults from Colombo, Sri Lanka." Hum Immunol.
2018;79(2):87-88. doi:10.1016/j.humimm.2017.12.007. PMID:29289740 (Allele Frequencies Net
Database population 3423). Carrier frequencies were counted directly from AFND's raw
ambiguity-resolved genotype export, not transcribed from the paper's summary table, and
collapsed through this codebase's own `hla_antigen_designation()` convention so the reference
table and this system's live typing data use identical antigen naming. See that module's
docstring for the full methodology, the DQA1/DPA1/DRB3,4,5 exclusion rationale, and the
disclosed linkage-disequilibrium limitation (single-locus frequencies combined as if
independent, which they aren't — a known, disclosed approximation, not silently ignored).

## 6. Donor safety-assessment model (`app/reference_data/donor_risk_model.py`)

**Externally published, independently verifiable — no changes needed here, referenced for
completeness.** Source: Grams ME, Sang Y, Levey AS, et al. "Kidney-Failure Risk Projection for
the Living Kidney-Donor Candidate." N Engl J Med 2016;374:411-421. doi:10.1056/NEJMoa1510491.
Every coefficient, spline knot, and base-case risk value in that module is transcribed verbatim
from the paper's Supplementary Appendix, Sections 3-4 — not reconstructed from memory or a
secondary source. See that module's docstring for the model's validated-population limitation
(US cohorts, Black/White only — "other" race is scored as an explicitly-flagged extrapolation,
never a silent third category) and `app/services/donor_risk_service.py`'s docstring for how it's
used, including the `values_outside_model_range` extrapolation flag for eGFR/BMI/ACR/SBP values
outside the model's own validated input range.

## 7. LKDPI — Living Kidney Donor Profile Index (`app/reference_data/lkdpi_model.py`)

**Externally published, independently verifiable — no changes needed here, referenced for
completeness.** Source: Massie ME, Leanza J, Fahmy LM, et al. "A Risk Index for Living Donor
Kidney Transplantation." Am J Transplant 2016;16(7):2077-2084. doi:10.1111/ajt.13709. All 13
coefficients in that module were checked directly against the paper's own full-text formula
(PMC6114098, the NIH PubMed Central mirror) on 2026-08-10, not reconstructed from a secondary
summary. See that module's docstring for the full coefficient table, the model's near-chance
external discrimination (C-statistic 0.55 in both the European and Canadian validation cohorts),
and the absence of any South Asian validation.

The four display bands below the score, however, are **this project's own convention, not
clinical policy** — Massie 2016 reports a median LKDPI of 12.8 (IQR -0.8 to 27.2) in the US
derivation cohort but does not itself define risk bands:

| Band | LKDPI | Meaning |
|---|---|---|
| Excellent | < 0 | Better than any deceased-donor kidney (~24% of US living donors) |
| Good | 0 – 20 | Better than roughly 80% of deceased-donor kidneys |
| Moderate | 20 – 40 | Around the median deceased donor |
| Marginal | ≥ 40 | Worse than the median deceased donor (~4% of US living donors scored above 50) |

If the doctors this app serves want different band boundaries, theirs win — update
`LKDPI_BANDS` in `lkdpi_model.py` and this table together.

---

## What to do if you're revisiting these numbers

- **§1, §2 (locus weights, sensitization weights)**: these need the original project
  specification slides to re-derive or change with confidence. Don't hand-edit them from memory
  or "what sounds right" — that's exactly the transcription risk this doc exists to flag.
- **§3, §4 (mismatch buckets, DSA bands)**: these are this codebase's own design decisions
  (bucket boundaries, banding structure) applied to a simpler, locally-justified rule set — safe
  to revise with a clear write-up of the new reasoning, same as any other application logic.
- **§5, §6 (cPRA frequencies, donor risk model), §7 (LKDPI coefficients)**: re-derive from the
  cited paper directly, never from this repo's transcription of it, if the numbers are ever in
  question. The LKDPI *bands* (unlike its coefficients) are a project convention and can be
  revised by the doctors this app serves without re-checking the paper.
