# prompts.py
#
# One prompt + expected JSON shape per document type, matching the EXACT
# field names ocr-service's current PaddleOCR-based extraction already
# produces (checked directly against app/extraction/demographics.py,
# hla.py, mfi_extraction.py, crossmatch_extraction.py on 2026-07-30).
# Keeping the shape identical is deliberate — Phase 2 of the migration plan
# freezes this as the external contract, so scoring against it now doubles
# as an early check that the shape is actually usable.

# Canonical locus set — must match kidney-backend's app/reference_data/hla_loci.py
# and ocr-service's app/reference_data/hla_loci.py exactly. A model that
# invents a locus value outside this set (or splits "DRB3,4,5" into three)
# is wrong in the same way the old PaddleOCR pipeline was wrong before this
# session's fixes.
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
    {"antigen": "<value from the Sero column>", "mfi": <value from the MFI/Baseline column as a number>},
    ...
  ]
}

Rules:
- Use the "Sero" column value for "antigen" (not the Bead code, not the
  Allele Equiv column — those are extra detail this system doesn't need
  right now).
- "mfi" must be a plain number (no commas, no units) — e.g. "23,706.91"
  becomes 23706.91.
- Include every row visible on this page, even ones with very small or
  zero MFI values near the bottom of the table.
- If a row's MFI is genuinely illegible, still include the antigen with
  "mfi": null rather than dropping the row entirely — a missing row is a
  worse failure than an uncertain number, since a downstream reviewer can
  spot-check a flagged null far more easily than notice something that was
  silently never mentioned at all.

Respond with ONLY the JSON object above — no markdown fences, no
explanation, no extra text.
"""
