# app/reference_data/exchange_weight_policies.py
"""
Cycle weights for exchange_matching_service.py's "equity_weighted" policy.

Every transplanted pair earns BASE_TRANSPLANT_WEIGHT (so the policy still
mostly rewards transplant volume, same direction as "max_transplants"), plus
two equity bonuses layered on top, mirroring the two factors real kidney-
paired-donation allocation schemes commonly credit: how hard the patient is
to match (cPRA) and how long they've waited.

CPRA_WEIGHT bonus uses calculate_cpra() (app/services/cpra_service.py) fed
by each patient's own unacceptable-antigen profile — a highly sensitised
patient is disproportionately hard to match outside a cycle that happens to
clear their antibodies, so a cycle that transplants them is worth more.

WAIT_WEIGHT bonus is a *disclosed approximation*: this codebase has no
dedicated "on dialysis since" or "waiting list since" field, only
Patient.created_at (when the patient was registered in this system, not
when they actually started waiting for a kidney). Real allocation waiting-
time credit is why patients "with a dialysis start date" matters — this is
a proxy for that (like the cPRA linkage-disequilibrium approximation
disclosed in cpra_service.py), not a fix. Fine for the comparison research
script's synthetic data (registration IS the simulated clock there) and for
demonstrating the policy shape; a real deployment would need a real
waiting-time field.
"""

BASE_TRANSPLANT_WEIGHT = 1.0
CPRA_WEIGHT = 1.0
WAIT_WEIGHT = 1.0

# Days of registration-date "waiting" needed to earn the full WAIT_WEIGHT
# bonus; longer waits don't earn more than that (capped 0..1 fraction).
WAIT_NORMALIZATION_DAYS = 365 * 3
