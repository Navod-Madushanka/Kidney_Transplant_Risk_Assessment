# app/reference_data/hla_loci.py
#
# Must mirror kidney-backend's app/reference_data/hla_loci.py exactly —
# that copy is the real canonical list (used for the DB-level HLALocusEnum,
# scoring weights, and the frontend's HLA_LOCUS_OPTIONS).
#
# As of the OCR -> local vision-LLM migration (see
# claude/ocr-to-local-llm-migration-plan.md), this list's role changed:
# it used to be what extract_hla()'s column-clustering tried to MATCH
# against (a header string had to squash down to one of these exactly).
# Now it's a VALIDATOR — app/extraction/llm_extract.py checks every locus
# the model returns against this set and drops/flags anything outside it,
# so a model hallucinating a locus spelling doesn't silently corrupt the
# response. Same list, different job.
HLA_LOCI = {
    "A",
    "B",
    "C",
    "DRB1",
    "DRB3,4,5",
    "DQA1",
    "DQB1",
    "DPA1",
    "DPB1",
}
