# app/reference_data/hla_loci.py
#
# Must mirror kidney-backend's app/reference_data/hla_loci.py exactly —
# that copy is the real canonical list (used for the DB-level HLALocusEnum,
# scoring weights, and the frontend's HLA_LOCUS_OPTIONS), and this service's
# extract_hla() only ever succeeds at matching a column header when the
# squashed header text lands on one of these values.
#
# This previously listed "DRB3", "DRB4", "DRB5" as three separate entries
# instead of the single combined "DRB3,4,5" the rest of the system actually
# uses — meaning extract_hla() could never produce a locus value the wizard
# would recognize for that column, so DRB3/4/5 silently never extracted
# from any document, regardless of how the report printed that column.
# Fixed 2026-07-30 by matching the canonical list exactly.
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