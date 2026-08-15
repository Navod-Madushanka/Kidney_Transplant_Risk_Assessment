# app/tests/unit/test_llm_schemas.py
#
# app/llm/schemas.py is hand-maintained separately from prompts.py's own
# "Extract into this exact JSON shape" prose (see schemas.py's module
# docstring for why: touching prompt wording without re-running the spike's
# fixtures is explicitly warned against, so schemas can't be generated FROM
# the prompt text). These tests are what keep the two from silently
# drifting apart: each hardcodes the field set the matching prompt's shape
# block documents and asserts both that the schema's own properties match
# it, AND that every field name is still literally present in the prompt
# text -- so editing either one without the other fails here instead of
# only being caught by a human re-reading both side by side.
from app.llm.prompts import BEAD_SPECIFICITY_PROMPT, CROSSMATCH_PROMPT, HLA_TYPING_PROMPT
from app.llm.schemas import BEAD_SPECIFICITY_SCHEMA, CROSSMATCH_SCHEMA, HLA_TYPING_SCHEMA

_PERSON_DETAILS_FIELDS = {"full_name", "nic_number", "date_of_birth", "blood_type", "hla_ref_no"}
_HLA_ENTRY_FIELDS = {"locus", "allele_1", "allele_2"}
_CROSSMATCH_RESULT_FIELDS = {"t_cell_result", "b_cell_result", "interpretation", "remarks", "test_date"}
_BEAD_ROW_FIELDS = {"bead", "antigen", "mfi"}


def _assert_fields_present_in_prompt(fields: set[str], prompt: str) -> None:
    missing = {field for field in fields if field not in prompt}
    assert not missing, f"fields {missing} not found anywhere in the prompt text"


def test_hla_typing_schema_matches_prompt_shape():
    assert set(HLA_TYPING_SCHEMA["properties"]) == {
        "patient_details", "donor_details", "patient_hla", "donor_hla",
    }
    assert set(HLA_TYPING_SCHEMA["properties"]["patient_details"]["properties"]) == _PERSON_DETAILS_FIELDS
    assert set(HLA_TYPING_SCHEMA["properties"]["donor_details"]["properties"]) == _PERSON_DETAILS_FIELDS
    assert set(HLA_TYPING_SCHEMA["properties"]["patient_hla"]["items"]["properties"]) == _HLA_ENTRY_FIELDS
    assert set(HLA_TYPING_SCHEMA["properties"]["donor_hla"]["items"]["properties"]) == _HLA_ENTRY_FIELDS

    _assert_fields_present_in_prompt(
        {"patient_details", "donor_details", "patient_hla", "donor_hla", *_PERSON_DETAILS_FIELDS, *_HLA_ENTRY_FIELDS},
        HLA_TYPING_PROMPT,
    )


def test_crossmatch_schema_matches_prompt_shape():
    assert set(CROSSMATCH_SCHEMA["properties"]) == {"patient_details", "donor_details", "crossmatch"}
    assert set(CROSSMATCH_SCHEMA["properties"]["patient_details"]["properties"]) == _PERSON_DETAILS_FIELDS
    assert set(CROSSMATCH_SCHEMA["properties"]["donor_details"]["properties"]) == _PERSON_DETAILS_FIELDS
    assert set(CROSSMATCH_SCHEMA["properties"]["crossmatch"]["properties"]) == _CROSSMATCH_RESULT_FIELDS

    _assert_fields_present_in_prompt(
        {"patient_details", "donor_details", "crossmatch", *_PERSON_DETAILS_FIELDS, *_CROSSMATCH_RESULT_FIELDS},
        CROSSMATCH_PROMPT,
    )


def test_bead_specificity_schema_matches_prompt_shape():
    assert set(BEAD_SPECIFICITY_SCHEMA["properties"]) == {"bead_specificity"}
    assert (
        set(BEAD_SPECIFICITY_SCHEMA["properties"]["bead_specificity"]["items"]["properties"])
        == _BEAD_ROW_FIELDS
    )

    _assert_fields_present_in_prompt(
        {"bead_specificity", *_BEAD_ROW_FIELDS}, BEAD_SPECIFICITY_PROMPT,
    )


def test_bead_row_bead_and_mfi_are_nullable_matching_the_prompts_null_contract():
    # BEAD_SPECIFICITY_PROMPT explicitly instructs "mfi": null / "bead":
    # null for an illegible value rather than dropping the row -- a schema
    # that didn't allow null here would make constrained decoding actively
    # fight the prompt's own instruction.
    bead_row_schema = BEAD_SPECIFICITY_SCHEMA["properties"]["bead_specificity"]["items"]
    assert bead_row_schema["properties"]["bead"]["type"] == ["string", "null"]
    assert bead_row_schema["properties"]["mfi"]["type"] == ["number", "null"]
    assert bead_row_schema["properties"]["antigen"]["type"] == "string"
