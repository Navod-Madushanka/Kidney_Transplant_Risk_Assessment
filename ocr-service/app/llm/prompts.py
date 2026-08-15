# app/llm/prompts.py
#
# One prompt + expected JSON shape per document type. Ported directly from
# llm-migration-spike/prompts.py, validated in Phase 1 against the real
# sample documents (HLA typing: 64/64 fields; crossmatch: 14/15; bead
# specificity: see the migration plan's Phase 1 Results for the honest
# numbers there). Do not "clean up" the wording here without re-running the
# spike's fixtures against the change first — several of the odd-looking
# instructions (the DRB3,4,5 special case, the exactly-9-loci checklist)
# exist because of specific failure modes observed during validation, not
# because they read elegantly.
#
# Field names match kidney-backend/kidney-frontend's frozen external
# contract exactly — see claude/ocr-to-local-llm-migration-plan.md.

# Canonical locus set — must match kidney-backend's app/reference_data/hla_loci.py
# and this service's app/reference_data/hla_loci.py exactly.
CANONICAL_HLA_LOCI = ["A", "B", "C", "DRB1", "DRB3,4,5", "DQA1", "DQB1", "DPA1", "DPB1"]

JSON_ONLY_INSTRUCTION = (
    "Respond with ONLY a single valid JSON object matching the shape below — "
    "no markdown code fences, no explanation, no extra text before or after "
    "the JSON. If a field is illegible or not present, use an empty string "
    "\"\" (for text fields) rather than guessing or omitting the key."
)

HLA_TYPING_PROMPT = f"""You are reading a Histocompatibility (HLA) Type-match Report — a lab
document with a "Patient Particulars" box and a "Donor Particulars" box at
the top, and a table below headed "Locus" with columns for each HLA locus
and rows for "Patient" and "Donor".

Extract into this exact JSON shape:

{{
  "patient_details": {{"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}},
  "donor_details": {{"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}},
  "patient_hla": [{{"locus": "", "allele_1": "", "allele_2": ""}}, ...],
  "donor_hla": [{{"locus": "", "allele_1": "", "allele_2": ""}}, ...]
}}

"patient_hla" and "donor_hla" MUST each contain EXACTLY 9 entries — one for
every single locus column in the table, never fewer. This table always has
these 9 locus columns, in roughly this left-to-right order: A, B, C, DRB1,
DRB3,4,5, DQA1, DQB1, DPA1, DPB1. Before you finish, count the entries in
each array — if either has fewer than 9, you stopped partway through the
table; go back and read the remaining columns you skipped rather than
submitting an incomplete list. A locus is illegible is still reported (with
allele_1/allele_2 as "") rather than left out — omitting the row entirely
is a worse failure than flagging it as unreadable.

Rules:
- "hla_ref_no" is the "Laboratory Reference" value in the particulars box
  (NOT the "Institution Serial").
- Every locus column in the table must be reported under EXACTLY one of
  these canonical locus names, even if the header is printed differently
  (e.g. "HLA-A*" means locus "A"; "HLA DRB1*" means locus "DRB1"; a combined
  "HLA-DRB3,4,5*" column means locus "DRB3,4,5" — do NOT split it into
  DRB3/DRB4/DRB5 separately): {CANONICAL_HLA_LOCI}
- Watch for OCR-style character confusion in your own reading of small
  print: the digit "1" is sometimes visually similar to a capital "I" in
  locus codes — "DRB1"/"DQA1" should always use the digit 1, never the
  letter I.
- If two adjacent locus columns appear visually merged or printed close
  together (e.g. "DPA1" and "DPB1" side by side), still report them as two
  SEPARATE entries in the array — read each column's own data cells even if
  their headers are close together.
- allele_1/allele_2 are the two comma-separated values printed in that
  locus's cell for that row (e.g. cell reads "03, 04" -> allele_1="03",
  allele_2="04").
- SPECIAL CASE — the "DRB3,4,5" locus is formatted differently from every
  other locus in this table: its two values are NOT plain numbers. They
  always start with "DRB3", "DRB4", or "DRB5" followed by "*" and two
  digits — e.g. "DRB3*02, DRB4*01" or "DRB3*01, DRB3*02". If what you're
  about to write for this locus's allele_1/allele_2 looks like a plain
  two-digit number (e.g. "03", "04") with no "DRB" prefix, you have
  almost certainly misread a neighboring column (most likely DRB1, which
  DOES use plain two-digit numbers and sits right next to this column) —
  look again specifically for the "DRB3*"/"DRB4*"/"DRB5*" text.

{JSON_ONLY_INSTRUCTION}
"""

CROSSMATCH_PROMPT = f"""You are reading a Histocompatibility / Crossmatch Report — a lab document
with "Patient Details" and "Donor Details" sections, followed by leukocyte
crossmatch results and an interpretation.

Extract into this exact JSON shape:

{{
  "patient_details": {{"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}},
  "donor_details": {{"full_name": "", "nic_number": "", "date_of_birth": "", "blood_type": "", "hla_ref_no": ""}},
  "crossmatch": {{
    "t_cell_result": "",
    "b_cell_result": "",
    "interpretation": "",
    "remarks": "",
    "test_date": ""
  }}
}}

Rules:
- "hla_ref_no" comes from a "HLA Ref No" or "Laboratory Reference" field.
- "t_cell_result"/"b_cell_result" are typically "Compatible" or
  "Incompatible" (sometimes phrased as Negative/Positive — transcribe
  whatever word is actually printed, don't normalize it).
- "interpretation" is the full sentence describing the overall crossmatch
  conclusion, not just a single word.
- "test_date" is whatever date is printed near a signature/report date
  field, in whatever format it's printed in (don't reformat it).

{JSON_ONLY_INSTRUCTION}
"""

# REVERTED 2026-08-01: this briefly carried two untested Phase 3 edits (an
# added "don't repeat rows" instruction, and "ONE PAGE" reworded to "ONE
# ROW-BAND TILE") that were never re-scored against the fixtures before
# shipping. A real run against sample_mfi_page1.jpg scored 1/13 anchors
# matched with those changes in place (2/8 tiles failed) — a sharp
# regression from Phase 1's validated 10/13 on the exact same page/model/
# tiling. Reverted to the exact wording Phase 1 validated as the obvious
# first suspect.
#
# UPDATE 2026-08-01: the revert did NOT clearly fix it — a retest on the
# reverted (Phase-1-identical) wording scored 2/13 with 5/8 tiles failed,
# i.e. worse tile-failure count than the version with the edits. That
# rules out prompt wording as the (sole) explanation. The tile-failure
# jump instead lines up with a concurrency bug: extract_bead_specificity
# was firing all 8 tiles via unbounded asyncio.gather against an Ollama
# server that only processes one request at a time (OLLAMA_NUM_PARALLEL=1,
# seen in the ollama container's own startup logs) — see the
# CONCURRENT_TILE_LIMIT comment in app/extraction/llm_extract.py for the
# full mechanism and the fix. Keeping this prompt at the Phase-1-validated
# wording regardless, since there's no evidence it needs to change — just
# don't treat the earlier "prompt wording is the prime suspect" framing
# above as confirmed; it wasn't.
# TRIED AND REVERTED 2026-08-04 (Phase 1 speed pass): briefly switched this
# prompt to a "rows_csv": "<mfi>,<antigen>\n..." single-string CSV envelope
# instead of the JSON array below, on the theory that a CSV line costs
# roughly half the tokens of a JSON object per row and output-token volume
# is the confirmed real bottleneck (see project memory
# ocr-extraction-speed-investigation). Real live test against
# sample_mfi_page1.jpg (uv run pytest -m integration -v -s
# test_bead_specificity_live.py) falsified this HARD: 0/13 anchors matched
# on all 3 repeated runs (previously this page swung noisily between
# 1/13-10/13 across attempts — a clean, deterministic zero every time is a
# different, worse signature). Captured the raw model output directly: the
# model correctly emitted the first 3 rows, then degenerated into repeating
# the same "23706.91,DP1" line hundreds of times until hitting the
# num_predict=1536 cap mid-string, on both the original attempt AND the
# JSON-retry (eval_count=1536 exactly, both times) -- a repetition-loop
# hallucination, the exact failure mode tiling+repeat_penalty=1.1 already
# exist to fight for the JSON format. The CSV format's shorter, more
# uniform per-row tokens appear to make the model MORE prone to this loop,
# not less -- each JSON object's extra scaffolding tokens (quotes, keys,
# colons) apparently break up the exact-repeat sequence better than bare
# CSV lines do. Also much SLOWER end to end (86min vs the ~40min RUNS=3
# baseline) from repeated failed-tile retries, not faster. Page 2 did not
# fail as badly (7/12, consistent across runs) -- this is data-dependent,
# not a wording typo, so don't just tweak the CSV wording and retry without
# a real mechanism for why it'd behave differently. If output-token volume
# is revisited again, a per-request retry-with-lower-repeat-penalty or a
# hard mid-generation repeat detector is a more promising angle than
# switching the wire format.
BEAD_SPECIFICITY_PROMPT = """You are reading ONE PAGE of a "Bead Specificity Chart" — a dense lab
report table with four columns: "Bead" (a 3-digit code), "Sero" (a short
antigen name like "A23", "B45,Bw6", "DQ4", "DP1"), "Allele Equiv" (one or
more full allele designations like "A*23:01" or "DQB1*04:02,DQA1*02:01"),
and "MFI" / "Baseline" (a decimal number, e.g. "23,706.91"). Rows are
sorted from highest MFI at the top of the page to lowest/zero at the
bottom. This image is a photo of a printed page and may be somewhat blurry
or low-contrast — read carefully and do your best on hard-to-read digits
rather than skipping the row.

Extract EVERY row on this page into this exact JSON shape:

{
  "bead_specificity": [
    {"bead": "<the 3-digit Bead code>", "antigen": "<value from the Sero column>", "mfi": <value from the MFI/Baseline column as a number>},
    ...
  ]
}

Rules:
- "bead" is the value from the "Bead" column (a 3-digit code, e.g. "011")
  — this is the row's unique identity on this page, since the same Sero
  value legitimately appears on several different beads (e.g. beads 011
  and 012 can both read "A24" at different MFI values — they are two
  distinct rows, not a duplicate).
- Use the "Sero" column value for "antigen" (not the Allele Equiv column
  — that's extra detail this system doesn't need right now).
- "mfi" must be a plain number (no commas, no units) — e.g. "23,706.91"
  becomes 23706.91.
- Include every row visible on this page, even ones with very small or
  zero MFI values near the bottom of the table.
- If a row's MFI is genuinely illegible, still include the bead/antigen
  with "mfi": null rather than dropping the row entirely — a missing row
  is a worse failure than an uncertain number, since a downstream
  reviewer can spot-check a flagged null far more easily than notice
  something that was silently never mentioned at all. The same applies to
  "bead": if it's illegible, still report the row with "bead": null
  rather than omitting it or guessing a number.

Respond with ONLY the JSON object above — no markdown fences, no
explanation, no extra text.
"""
