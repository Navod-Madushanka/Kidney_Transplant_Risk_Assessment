# Implementation prompt — Part I: Bead row identity, tile reconciliation, and the cPRA double-count

**Insert as Part I of `implementation-prompt.md`, after Part H. Everything below the line goes to your coding agent.**

---

## I0. Confirmed — and the column that would have prevented it

The finding under review is correct: overlapping tiles re-extract the same rows, near-miss MFI values defeat the dedup, and the result is silent duplicates or silent drops. Unlike Part H, there is nothing to correct in the diagnosis. There are four things to add to it.

**First: the source document already carries a primary key, and the prompt throws it away.** `ocr-service/app/llm/prompts.py`:

```
- Use the "Sero" column value for "antigen" (not the Bead code, not the
  Allele Equiv column — those are extra detail this system doesn't need
  right now).
```

The chart's four columns are **Bead** (a 3-digit code, unique within the panel), **Sero**, **Allele Equiv**, and **MFI/Baseline**. The prompt names all four so the model can locate the right one, then instructs it to return only `{antigen, mfi}`. So no stable row identity exists anywhere in the pipeline — not in the JSON, not in `antibody_profiles`, not in the UI.

**Second: the key that was chosen is built from a column that is non-unique by design.** On the real chart for patient 198001610076V, bead 011 is `A24 / A*24:02` at MFI 23,582.08 and bead 012 is `A24 / A*24:03` at 23,530.10. Two distinct beads, same Sero value. The same holds for A2 (three beads: A\*02:01, A\*02:03, A\*02:06), A68, B44, B60/B61 and most of the high-MFI block. **One serological group spanning several beads is the normal case on a single-antigen panel, not an edge case.** `(antigen, mfi)` was never going to identify a row; it only works when the MFI happens to differ, which is exactly what stops being true when a model re-reads the same row twice.

**Third: roughly a quarter of every page is affected.** `tiling.py` uses `DEFAULT_NUM_TILES = 8` and `DEFAULT_OVERLAP_FRAC = 0.12` applied to *each* side, so an interior tile spans ~124% of a band and about 24% of a page's rows are extracted twice. At ~100 rows per page that is ~24 double-read rows per page, ~48 per patient. This is the common path.

**Fourth, and worst: the dedup is masking the exact hallucination that tiling exists to prevent.** See I2.

---

## I1. What `_dedupe_rows` does, and the three ways it fails

```python
def _dedupe_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        ...
        mfi = _coerce_mfi(row.get("mfi"))
        key = (antigen.lower(), mfi)
        if key in seen: continue
        seen.add(key)
        out.append({"antigen": antigen, "mfi": mfi})
    return out
```

Exact float equality, first-wins. Three distinct failures:

| Input | Key behaviour | Result |
|---|---|---|
| Tile 3 reads `23706.91`, tile 4 reads `23706.9` for the same bead | Two distinct keys | **Duplicate created.** One physical bead becomes two antibody records. |
| Beads 011 and 012 are both `A24` and both read as the same MFI | One key, first wins | **Valid entry dropped.** A real bead vanishes with no trace. |
| Several illegible rows all yield `mfi: None` | `(antigen, None)` is a legal key | **All null-MFI rows for one antigen collapse to one**, regardless of how many beads were unreadable. |

The existing test `test_dedupe_keeps_same_antigen_different_mfi` passes only because its two MFIs differ. Every dedup test in `test_row_validation.py` uses byte-identical floats. **The near-miss case — the entire finding — has no coverage.**

---

## I2. Dedup is hiding the failure mode tiling was built to fix

`llm_extract.py` documents the reason for tiling: a single-shot read of the full table sends the model into a repetition loop, with *"six different labels all reported as the same 23706.91."*

Now trace a tile that degenerates the same way and emits 40 copies of one row:

1. The tile returns valid JSON, so `failed_tiles` does not increment — `failed_tiles` only counts tiles that raised `LLMExtractionError`.
2. `_dedupe_rows` sees 40 byte-identical rows and collapses them to one.
3. The page reports as a clean success with the standard blanket warning.

**A catastrophically degenerate tile is indistinguishable from a tile containing one row.** The dedup sits directly downstream of the known hallucination and erases its only signature. That is a more serious defect than the duplicate-creation the finding describes, and it is invisible in production today.

---

## I3. What an MFI error actually costs

From the codebase's own constants, so the tolerance rule in I5 is grounded rather than arbitrary:

- `app/reference_data/dsa_threshold.py`: `DSA_MFI_FLOOR = 1000.0`. Below it, an antibody is **not flagged as a DSA at all**. Bands: weak 1000–1999.99, moderate 2000–4999.99, then `DSA_HALTING_SEVERITY`.
- `app/services/dsa_service.py`: `DEFAULT_MFI_CUTOFF = 2000.0` for the cPRA sensitisation screen (deliberately not unified with the floor — see the `dsa_threshold` docstring).
- `check_dsa`: an antibody matching a donor antigen in the halting band sets `is_halted=True` and emits *"CRITICAL WARNING… Process halted due to very high risk of rejection."*

So a digit misread that crosses 1000 flips an antibody between invisible and flagged, and one that crosses into the halting band stops the transplant workflow. **The magnitude of an MFI error matters far less than which side of a threshold it lands on.** A 950↔1050 disagreement is 10% and clinically decisive; a 23706↔23709 disagreement is 0.01% and clinically irrelevant. Any tolerance rule that looks only at relative difference gets this backwards.

---

## I4. Fix 1 — capture the Bead ID

Change `BEAD_SPECIFICITY_PROMPT` to request the Bead column:

```json
{"bead": "<the 3-digit Bead code>", "antigen": "<Sero column>", "mfi": <number>}
```

Delete the instruction to ignore it. Keep the instruction to ignore Allele Equiv — that one is genuinely unused, and asking for less keeps the output narrower.

**Do not trust it blindly.** A 3-digit code in a dense column is itself misreadable. Validate on arrival in `llm_extract.py`:

- Must match `^\d{1,3}$` after stripping whitespace; normalise to zero-padded three digits so `44`, `044` and ` 44 ` unify.
- Must fall inside a plausible panel range (`1..120` is a safe bound for a single-antigen panel).
- **A row with an invalid or missing bead ID is kept, not dropped**, with `bead: None`, and counted in the coverage report. The prompt's existing stance — a missing row is a worse failure than an uncertain field — applies here too.

The bead ID becomes the *preferred* key with a graceful fallback to `(antigen, mfi)` for rows that lack one. Nothing in the pipeline may hard-depend on it being present.

---

## I5. Fix 2 — reconcile, don't dedupe

Replace `_dedupe_rows` with a reconciliation step that returns **both** merged rows and a report. Intended shapes only:

```python
@dataclass(frozen=True)
class BeadObservation:
    bead: str | None
    antigen: str
    mfi: float | None
    tile_index: int

@dataclass(frozen=True)
class ReconciledRow:
    bead: str | None
    antigen: str
    mfi: float | None
    observations: int
    conflict: tuple[float | None, ...] | None   # all candidate MFIs when tiles disagreed

def reconcile_bead_rows(
    observations: list[BeadObservation], num_tiles: int
) -> tuple[list[ReconciledRow], BeadReconciliationReport]:
```

Group by `bead` where present, falling back to `(antigen.lower(), mfi)` where absent. Then, per group:

| Case | Action |
|---|---|
| One observation | Take it. `observations=1`. |
| Several that **agree** | Merge to one. Record `observations=n`. No flag. |
| Several that **disagree** | Keep **one** row, take the **highest** MFI, populate `conflict` with every candidate, and add the bead to the report's conflict list. **Never silently pick.** |

Agreement rule — both conditions must hold:

```python
def _agree(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if _clinical_band(a) != _clinical_band(b):   # 1000 / 2000 / halting boundary
        return False                              # threshold crossing always disagrees
    return abs(a - b) <= max(1.0, MFI_AGREEMENT_FRAC * max(a, b))
```

- `_clinical_band` must **import** `DSA_MFI_FLOOR` and the band edges from `app/reference_data/dsa_threshold.py`. Do not re-declare those numbers in ocr-service — they will drift, and a drifted copy silently changes which disagreements get flagged.

  This creates a dependency from ocr-service on a backend reference module. If that is unacceptable, pass the thresholds in the `/extract` request from the backend, which already owns them. **Do not copy-paste the constants.**
- `MFI_AGREEMENT_FRAC = 0.02`. OCR near-misses are ~0.01%; a transposed digit is ~15%; a dropped digit is ~90%. 2% separates noise from a genuinely different reading with wide margin on both sides. Make it a named constant.

**Why the highest value on conflict:** the row is flagged for mandatory review either way, so the chosen value is a default pending confirmation, not an answer. If review is skipped, over-flagging costs a clinician a second look; under-flagging risks missing a DSA. Erring high puts the residual risk on the recoverable side. Write that reasoning in the docstring, because it will look arbitrary in six months.

---

## I6. Fix 3 — report coverage and anomalies

This is the change that converts "silently dropping valid entries" into a condition the doctor can see. The report accompanies the rows:

```python
@dataclass(frozen=True)
class BeadReconciliationReport:
    observed_beads: int
    gaps: list[str]              # missing IDs inside the observed min..max run
    conflicts: list[BeadConflict]
    unreadable_mfi: list[str]    # bead IDs whose MFI could not be parsed
    no_bead_id: int
    degenerate_tiles: list[int]
```

- **Gap detection.** Bead IDs on a panel run as a near-contiguous sequence. Sort the observed set, and report any ID missing between min and max. "Read 97 beads; 031, 047 and 062 are missing" is a specific, checkable statement. Today a dropped bead leaves no trace at all.
- **Degenerate-tile detection**, closing I2. Flag a tile when either holds: ≥5 of its rows share an identical MFI to the cent, or it returns more than 3× the median row count of the other tiles. Report the tile index. Optionally re-run just that tile once before giving up — the infrastructure for a single-tile call already exists.
- **Replace the string-concatenated warning.** `warning = f"{failed_tiles}_of_{len(tiles)}_tiles_failed_{warning}"` cannot carry structure. Emit a list of `{code, detail, bead_ids}` objects instead. This changes the `/extract` response shape, so `OcrJobDocumentStatus`, `ocrNormalize.js` and the error-relay in `ocr_batch_service.py` all move together.
- **Keep the blanket verify warning, but stop making it the whole message.** A warning that fires on every single extraction is, behaviourally, no warning — the toggle gets flipped without reading. Specific warnings ("beads 044 and 051 disagreed between tiles"; "bead 062 missing") direct attention to the ~3 rows that need it instead of asking for ~100 to be re-read.

---

## I7. Fix 4 — page identity, and the trap in keying on bead ID

**Bead IDs repeat across the two pages.** On the real chart, bead 044 is `B76,Bw6 / B*15:12` on page 1 (Class I) and `DQ4 / DQB1*04:02,DQA1*02:01` on page 2 (Class II). They are two panels, each numbered from 001.

Today this is harmless by luck: `SLOT_DOCUMENT_TYPES` maps both slots to `document_type: "bead_specificity"`, the backend concatenates the two lists with no dedup at all, and Class I and Class II Sero names never collide. **Adopting bead ID as the key without page identity would convert that luck into a silent data-loss bug** — bead 044 from page 2 would be discarded as a duplicate of page 1's.

So:

- Stamp `page` (1 or 2) and `panel` (`class_i` / `class_ii`) onto every row. The **backend** does this — it knows the slot; ocr-service receives the same `document_type` for both and cannot tell them apart.
- Reconciliation runs **per page, inside ocr-service** (it has the tiles). The backend's cross-page step **must not dedupe**; it concatenates and then *asserts* that `(page, bead)` is unique, raising a warning if it is not.
- Derive `panel` from the slot, not from the content. Do not infer Class I vs Class II from antigen names — a misread `DQ4` as `B44` would silently reclassify the row.

---

## I8. Fix 5 — the null-MFI contract is broken in both directions

The prompt deliberately instructs the model to emit `mfi: null` rather than drop an illegible row. Both consumers violate that contract, in opposite ways:

- **The frontend silently discards them.** `normalizeOcrBatchResponse` does `.filter((entry) => entry.antigen && entry.mfi !== null)`. The row the prompt worked to preserve never reaches the doctor.
- **The backend crashes on them.** `AntibodyProfile.mfi` is `Numeric(10, 2), nullable=False` and `AntibodyProfileEntry.mfi` is a non-optional `Decimal`, but the registration-flow auto-save builds entries straight from the rows. **One null-MFI row raises a validation error that fails the entire job** — every other successfully-extracted document included.

Resolve it by treating a null MFI as an extraction artefact rather than a clinical fact:

- **Keep `antibody_profiles.mfi` NOT NULL.** It is compared against thresholds throughout `dsa_service`; making it nullable pushes `None` handling into every consumer for no benefit.
- **Frontend: stop filtering.** Render null-MFI rows with an empty, visibly-marked MFI field and a "couldn't read this value" note. They are the rows most in need of a human.
- **Backend auto-save: filter null-MFI rows out before building entries**, count them, and surface that count as a warning. A row that cannot be read must never fail the job.
- **Block the verification toggle** while any null-MFI row is unresolved. `needsVerification` already gates Continue; extend it so the doctor must supply or delete each unreadable value rather than confirming a chart with holes in it.

Minor, same file: `_coerce_mfi`'s `re.sub(r"[^\d.]", "", ...)` turns a European-formatted `"23.706,91"` into `"23.70691"` — a plausible-looking wrong number rather than a parse failure. Reject multi-dot strings explicitly.

---

## I9. Fix 6 — cPRA double-counts repeated antigens (independent live bug)

This one is not caused by tiling and exists in production right now. The finding above is what exposed it.

`get_patient_sensitized_antigens` returns every antigen whose `mfi > cutoff`, and `calculate_cpra` combines frequencies with `combined_frequency + f - (combined_frequency * f)` **without deduplicating the input list**.

Because one Sero group legitimately spans several beads (I0), a sensitised patient's list contains repeats. On the real chart, A24 appears on beads 011 and 012 at 23,582.08 and 23,530.10 — both far above the 2000 cutoff — so A24's frequency is combined twice, yielding `2f − f²` instead of `f`. A2 appears three times. Most of the high-MFI block repeats.

**cPRA is therefore overstated for essentially every sensitised patient**, independently of any OCR error. Fix: deduplicate by normalised antigen name before the frequency combination. It is close to a one-line change and it moves a number that drives allocation decisions — confirm the intended semantics with the referring clinician before shipping, and note the change in the audit log so historical cPRA values remain interpretable.

---

## I10. Data model and migration

`antibody_profiles` gains:

| Column | Type | Notes |
|---|---|---|
| `bead_id` | `String(3)`, nullable | Zero-padded. Nullable because a row with an unreadable bead code must still be storable. |
| `panel` | enum `class_i` / `class_ii`, nullable | From the slot, never inferred from content. |
| `extraction_conflict` | JSONB, nullable | Candidate MFIs when tiles disagreed. Preserves that the value was contested even after the doctor confirms one. |

Run as separate reviewable migration steps:

1. Add the three columns, all nullable. Existing rows keep NULLs — they predate bead capture and that is the honest representation.
2. Backfill nothing. There is no source to backfill from.
3. **Defer the partial unique index** `(patient_id, panel, bead_id) WHERE bead_id IS NOT NULL` to a follow-up, after reconciliation has run in production long enough to trust it. Added too early it converts a silent double-count into a failed job — a worse experience while the new path is still settling. Add it once the conflict rate is known.

---

## I11. Tests

**ocr-service**

- `test_row_validation.py` — the existing dedup cases stay, rewritten against `reconcile_bead_rows`. **Add the case the whole finding is about:** same bead across two tiles at `23706.91` and `23706.9` → **one** row, `observations=2`, no conflict. And `23706.91` vs `23708.91` under a threshold-crossing check → one row with `conflict` populated.
- Two distinct beads (011, 012) both `A24` with identical MFI → **two** rows. This is the drop case, and it is unrepresentable without bead IDs.
- Threshold crossing dominates relative tolerance: `990` vs `1010` is 2% but must be flagged as a conflict; `23706` vs `23709` must not.
- Degenerate tile: one tile returns 40 rows sharing an MFI → tile index appears in `degenerate_tiles` and the rows do **not** silently collapse to one clean row. This is the I2 regression test.
- Gap detection: observed beads `001..050` minus `031` → `gaps == ["031"]`.
- Invalid bead IDs (`"4"`, `"1044"`, `""`, `None`) → row retained with `bead=None`, counted in `no_bead_id`, never dropped.
- `test_bead_specificity_stream.py` — extend beyond the all-tiles-identical happy path to a mixed case with one conflict, one gap and one degenerate tile, asserting the structured warning list.
- **`tiling.py` has no geometry tests at all.** Add them: band heights sum to cover the full page, adjacent tiles overlap by `overlap_frac` of a band, first and last tiles clamp at the edges, and no horizontal pixel row is missed.

**The live harness is structurally blind to this bug and must change.** `test_bead_specificity_live_scoring.py` matches anchors by antigen name within **15% MFI tolerance**, which treats `23706.91` and `23708.91` as the same row — it cannot detect duplicate creation by construction. Add bead IDs to the anchor set and assert exact row count and exact bead-ID set, not fuzzy antigen matching.

**Backend**

- Cross-page merge: page 1 bead 044 and page 2 bead 044 both survive, with distinct `panel` values.
- A null-MFI row in the registration auto-save path is filtered and counted — **the job completes `DONE`**, not `FAILED`. This is a current crash.
- `calculate_cpra` with `["A24", "A24", "A2"]` equals the result for `["A24", "A2"]`.

**Frontend**

- Null-MFI rows render with an empty marked field instead of vanishing.
- Conflicted rows render both candidate values.
- Verification toggle stays disabled while any null-MFI row is unresolved.
- Gap and conflict warnings render as a specific list, not one blanket sentence.

---

## I12. Do not

- **Do not reduce or remove the tile overlap** to avoid double-reads. It exists so rows straddling a cut are not sliced in half. The fix is principled reconciliation, not less coverage.
- **Do not key on bead ID alone.** Bead 044 exists on both pages as different antibodies — see I7. The key is `(panel, bead_id)`.
- **Do not let dedup be silent.** Every collapse must be counted and every disagreement reported. Silent collapse is what turned a known hallucination into an invisible one.
- **Do not copy `DSA_MFI_FLOOR` or the band edges into ocr-service.** Import them or pass them in. A drifted copy changes which disagreements get flagged, with no test to catch it.
- **Do not make `antibody_profiles.mfi` nullable.** Handle unreadable rows at the review layer; do not push `None` into every threshold comparison in `dsa_service`.
- **Do not drop rows the model flagged as uncertain**, in either the frontend filter or the backend auto-save. The prompt preserves them deliberately.
- **Do not add the unique index in the first migration.** It turns a silent double-count into a failed job before the new path has earned trust.
- **Do not ship the cPRA dedup without telling the clinician.** It changes a number that has already been reported on real patients.
- **Do not rely on the existing live scoring harness to validate any of this.** Its 15% tolerance makes it blind to the exact failure mode.
