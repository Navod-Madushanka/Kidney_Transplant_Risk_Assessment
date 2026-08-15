# app/llm/schemas.py
"""JSON Schemas passed to Ollama's `format` field (constrained decoding --
see chat_json's `schema` parameter) -- one per document type, machine-
readable mirrors of the "Extract into this exact JSON shape" block each
prompt in prompts.py already describes in prose.

Kept as a SEPARATE source of truth from the prompt strings, not derived
from them: prompts.py's own module docstring warns against touching prompt
wording without re-running the spike's fixtures, and these shapes are
already validated prose embedded in carefully-tuned instructions (the
DRB3,4,5 special case, the exactly-9-loci checklist) -- turning that prose
into schema-generated text risks silently changing wording that scored
what it scores for reasons that aren't obvious from the wording alone. So
this file is hand-maintained instead, and
app/tests/unit/test_llm_schemas.py's test_*_schema_matches_prompt_shape
tests are what keep the two from drifting apart unnoticed: touching a
prompt's shape block without updating the matching schema here fails loudly
in CI rather than silently.

Field presence ("required") mirrors what each prompt instructs the model to
always include (e.g. "still include the bead/antigen with mfi: null rather
than dropping the row") -- required means "key must be present", not
"non-null"; nullable fields use a ["type", "null"] union instead.
"""

_PERSON_DETAILS_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "nic_number": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "blood_type": {"type": "string"},
        "hla_ref_no": {"type": "string"},
    },
    "required": ["full_name", "nic_number", "date_of_birth", "blood_type", "hla_ref_no"],
}

_HLA_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "locus": {"type": "string"},
        "allele_1": {"type": "string"},
        "allele_2": {"type": "string"},
    },
    "required": ["locus", "allele_1", "allele_2"],
}

HLA_TYPING_SCHEMA = {
    "type": "object",
    "properties": {
        "patient_details": _PERSON_DETAILS_SCHEMA,
        "donor_details": _PERSON_DETAILS_SCHEMA,
        "patient_hla": {"type": "array", "items": _HLA_ENTRY_SCHEMA},
        "donor_hla": {"type": "array", "items": _HLA_ENTRY_SCHEMA},
    },
    "required": ["patient_details", "donor_details", "patient_hla", "donor_hla"],
}

_CROSSMATCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "t_cell_result": {"type": "string"},
        "b_cell_result": {"type": "string"},
        "interpretation": {"type": "string"},
        "remarks": {"type": "string"},
        "test_date": {"type": "string"},
    },
    "required": ["t_cell_result", "b_cell_result", "interpretation", "remarks", "test_date"],
}

CROSSMATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "patient_details": _PERSON_DETAILS_SCHEMA,
        "donor_details": _PERSON_DETAILS_SCHEMA,
        "crossmatch": _CROSSMATCH_RESULT_SCHEMA,
    },
    "required": ["patient_details", "donor_details", "crossmatch"],
}

# bead/mfi are nullable -- BEAD_SPECIFICITY_PROMPT explicitly instructs the
# model to report "bead": null / "mfi": null for an illegible value rather
# than dropping the row (see llm_extract.py's Part I null-MFI contract).
_BEAD_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "bead": {"type": ["string", "null"]},
        "antigen": {"type": "string"},
        "mfi": {"type": ["number", "null"]},
    },
    "required": ["bead", "antigen", "mfi"],
}

BEAD_SPECIFICITY_SCHEMA = {
    "type": "object",
    "properties": {
        "bead_specificity": {"type": "array", "items": _BEAD_ROW_SCHEMA},
    },
    "required": ["bead_specificity"],
}
