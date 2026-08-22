# app/reference_data/versions.py
"""
One place collecting every clinical reference-data module's current version
string, so a single dict can be stamped onto MatchReport.reference_versions
at creation time (see app/services/match_report_service.py). That's what
lets a report generated today stay interpretable after a doctor-approved
change to, say, the DSA bands or the risk tiers next month -- the report
still says exactly which version of each table was in force when it was
computed, without having to diff full constant tables by hand.

Stamped unconditionally on every report, not just the modules a particular
pipeline run actually reached (e.g. an ABO-halted report never consults
DSA_SEVERITY_BANDS) -- it's a record of what was in force at generation
time, not a claim that every module's value influenced this report's
verdict. See docs/changing-clinical-constants.md for the procedure to
follow when one of these values changes.

Deliberately does not include app/reference_data/donor_risk_model.py or
app/reference_data/lkdpi_model.py: those are transcribed verbatim from
their source papers (Grams et al. NEJM 2016; Massie et al. AJT 2016) and
are not expected to change independent of a new edition of the paper itself
-- see docs/clinical-basis.md §§6-7.
"""
from app.reference_data.abo_compatibility import ABO_COMPATIBILITY_VERSION
from app.reference_data.dsa_threshold import DSA_THRESHOLD_VERSION
from app.reference_data.hla_antigen_frequencies import HLA_FREQUENCY_TABLE_VERSION
from app.reference_data.hla_weights import HLA_WEIGHTS_VERSION
from app.reference_data.mismatch_buckets import MISMATCH_BUCKETS_VERSION
from app.reference_data.pra_buckets import PRA_BUCKETS_VERSION
from app.reference_data.risk_classification import RISK_CLASSIFICATION_VERSION
from app.reference_data.risk_tiers import RISK_TIERS_VERSION
from app.reference_data.sensitization_weights import SENSITIZATION_WEIGHTS_VERSION

CLINICAL_REFERENCE_VERSIONS: dict[str, str] = {
    "abo_compatibility": ABO_COMPATIBILITY_VERSION,
    "dsa_threshold": DSA_THRESHOLD_VERSION,
    "hla_antigen_frequencies": HLA_FREQUENCY_TABLE_VERSION,
    "hla_weights": HLA_WEIGHTS_VERSION,
    "mismatch_buckets": MISMATCH_BUCKETS_VERSION,
    "pra_buckets": PRA_BUCKETS_VERSION,
    "risk_classification": RISK_CLASSIFICATION_VERSION,
    "risk_tiers": RISK_TIERS_VERSION,
    "sensitization_weights": SENSITIZATION_WEIGHTS_VERSION,
}
