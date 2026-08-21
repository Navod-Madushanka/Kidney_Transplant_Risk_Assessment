#!/usr/bin/env python
"""
Standalone research script -- no database, no HTTP. Builds a reproducible
synthetic paired-exchange pool, runs the exchange matcher
(app/services/exchange_matching_service.py) under all three weight
policies, and writes a comparison report to
kidney-backend/research/exchange_policy_comparison.md.

This is the deliverable the exchange-engine build asked for: not just "how
many transplants per policy" but *which* simulated patients each policy
actually transplants -- the real trade-off a program coordinator weighs.
equity_weighted is expected to sacrifice some raw transplant count relative
to max_transplants/max_quality in exchange for reaching highly-sensitized
and long-waiting patients those two policies are structurally biased
against: a hard-to-match patient completes fewer compatible edges in the
first place, so a policy that doesn't credit them extra tends to leave them
in the pool indefinitely even when a cycle including them exists.

Run: uv run python scripts/exchange_policy_comparison.py
"""
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.models.donor import Donor
from app.models.donor_hla_typing import DonorHLATyping
from app.models.enums import (
    BloodType,
    DonorStatus,
    HLALocusEnum,
    Race,
    RhFactor,
    Sex,
    SmokingStatus,
)
from app.models.patient import Patient
from app.models.patient_hla_typing import PatientHLATyping
from app.reference_data.abo_compatibility import ABO_COMPATIBILITY
from app.services.dsa_service import PatientAntibody
from app.services.exchange_graph_service import ExchangePairNode, build_exchange_graph
from app.services.exchange_matching_service import (
    WEIGHT_POLICIES,
    build_graph_index,
    cpra_fraction,
    score_cycle,
    solve_exchange_matching,
)

RANDOM_SEED = 20260809
POOL_SIZE = 40

BLOOD_TYPES = [BloodType.O, BloodType.A, BloodType.B, BloodType.AB]

# Small synthetic allele pools for the 3 mismatch-counted loci -- enough
# variety that real mismatch counts (0-6) come up across the pool without
# every pair being either a perfect match or a total clash.
ALLELE_POOL = {
    "A": ["01", "02", "03", "11", "24", "33"],
    "B": ["07", "08", "35", "40", "44", "58"],
    "DRB1": ["01", "03", "04", "07", "13", "15"],
}

# Serological antigen designations that are real keys in
# HLA_ANTIGEN_FREQUENCIES (see hla_typing_service.hla_antigen_designation
# for the real locus->prefix mapping this mirrors) -- so synthetic patient
# antibody profiles produce a real, differentiated cPRA spread rather than
# antigens the frequency table can't recognize.
ANTIBODY_ANTIGEN_POOL = [
    "A24", "A2", "A1", "B7", "B35", "B44", "B58", "DR15", "DR7", "DR4", "DR13",
]

MAX_WAIT_DAYS = 4 * 365


@dataclass
class SimulatedPool:
    nodes: list[ExchangePairNode]
    donor_typing_entries_by_donor: dict
    patient_typing_entries_by_patient: dict
    patient_antibodies_by_patient: dict
    pair_labels: dict[uuid.UUID, str]


def _pick_incompatible_pair(rng: random.Random) -> tuple[BloodType, BloodType]:
    """Picks a (patient, donor) blood type combination whose DIRECT pairing
    fails ABO -- the exchange pool's entry criterion (see
    exchange_graph_service.load_exchange_pool). Simplified from the real
    filter, which also checks mismatch/DSA, since this script builds nodes
    directly rather than going through that DB-facing filter."""
    while True:
        patient_bt = rng.choice(BLOOD_TYPES)
        donor_bt = rng.choice(BLOOD_TYPES)
        if donor_bt.value not in ABO_COMPATIBILITY[patient_bt.value]:
            return patient_bt, donor_bt


def _random_typing_rows(rng: random.Random, model, owner_field: str, owner_id: uuid.UUID) -> list:
    rows = []
    for locus, pool in ALLELE_POOL.items():
        allele_1, allele_2 = rng.sample(pool, 2)
        rows.append(
            model(
                **{owner_field: owner_id},
                locus=HLALocusEnum(locus),
                allele_1=allele_1,
                allele_2=allele_2,
            )
        )
    return rows


def _random_antibodies(rng: random.Random, sensitization: str) -> list[PatientAntibody]:
    """`sensitization` in {"low", "moderate", "high"} controls how many
    antigens get flagged, spreading cPRA across the simulated pool instead
    of leaving every patient equally (un)sensitized."""
    low, high = {"low": (0, 1), "moderate": (1, 3), "high": (3, 6)}[sensitization]
    count = rng.randint(low, high)
    antigens = rng.sample(ANTIBODY_ANTIGEN_POOL, min(count, len(ANTIBODY_ANTIGEN_POOL)))
    return [PatientAntibody(antigen=antigen, mfi=rng.uniform(500, 8000)) for antigen in antigens]


def build_synthetic_pool(seed: int = RANDOM_SEED, size: int = POOL_SIZE) -> SimulatedPool:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)

    nodes: list[ExchangePairNode] = []
    donor_typing_entries_by_donor = {}
    patient_typing_entries_by_patient = {}
    patient_antibodies_by_patient = {}
    pair_labels: dict[uuid.UUID, str] = {}

    for i in range(size):
        patient_bt, donor_bt = _pick_incompatible_pair(rng)
        doctor_id = uuid.uuid4()
        hospital_name = f"Simulated Hospital {i % 6 + 1}"

        # LKDPI inputs (app/services/lkdpi_service.py) -- randomized so
        # weight_max_lkdpi_quality has a real, differentiated signal to rank
        # edges by, same purpose as the mismatch/antibody randomization
        # above. Donor age randomized 28-70, derived into a date_of_birth.
        donor_dob = date.today() - timedelta(days=rng.randint(28, 70) * 365)
        donor = Donor(
            id=uuid.uuid4(),
            doctor_id=doctor_id,
            full_name=f"Sim Donor {i}",
            date_of_birth=donor_dob,
            blood_type=donor_bt,
            rh_factor=RhFactor.POSITIVE,
            status=DonorStatus.AVAILABLE,
            is_deleted=False,
            hla_typing_verified=True,
            egfr=rng.uniform(60, 110),
            bmi=rng.uniform(20, 32),
            race=rng.choices([Race.BLACK, Race.WHITE, Race.OTHER], weights=[0.1, 0.6, 0.3])[0],
            smoking_status=rng.choices(
                [SmokingStatus.NEVER, SmokingStatus.FORMER, SmokingStatus.CURRENT],
                weights=[0.6, 0.25, 0.15],
            )[0],
            systolic_bp=rng.uniform(105, 145),
            sex=rng.choice([Sex.MALE, Sex.FEMALE]),
            weight_kg=rng.uniform(55, 95),
            is_biologically_related=rng.random() < 0.7,
        )

        registered_days_ago = rng.randint(0, MAX_WAIT_DAYS)
        patient = Patient(
            id=uuid.uuid4(),
            doctor_id=doctor_id,
            full_name=f"Sim Patient {i}",
            date_of_birth=date(1970, 1, 1),
            blood_type=patient_bt,
            rh_factor=RhFactor.POSITIVE,
            is_deleted=False,
            hla_typing_verified=True,
            antibody_profile_verified=True,
            created_at=now - timedelta(days=registered_days_ago),
            sex=rng.choice([Sex.MALE, Sex.FEMALE]),
            weight_kg=rng.uniform(50, 90),
        )

        node = ExchangePairNode(
            donor=donor,
            patient=patient,
            donor_hospital_name=hospital_name,
            donor_doctor_full_name=f"Dr. Sim {i}",
            donor_doctor_email=f"sim{i}@example.com",
            patient_hospital_name=hospital_name,
            patient_doctor_full_name=f"Dr. Sim {i}",
            patient_doctor_email=f"sim{i}@example.com",
        )
        nodes.append(node)

        sensitization = rng.choices(["low", "moderate", "high"], weights=[0.6, 0.3, 0.1])[0]
        patient_antibodies_by_patient[patient.id] = _random_antibodies(rng, sensitization)
        pair_labels[node.pair_id] = (
            f"Pair {i:02d} ({patient_bt.value} recipient / {donor_bt.value} donor, "
            f"waiting {registered_days_ago}d, {sensitization} sensitization)"
        )

        donor_typing_entries_by_donor[donor.id] = _random_typing_rows(
            rng, DonorHLATyping, "donor_id", donor.id
        )
        patient_typing_entries_by_patient[patient.id] = _random_typing_rows(
            rng, PatientHLATyping, "patient_id", patient.id
        )

    return SimulatedPool(
        nodes=nodes,
        donor_typing_entries_by_donor=donor_typing_entries_by_donor,
        patient_typing_entries_by_patient=patient_typing_entries_by_patient,
        patient_antibodies_by_patient=patient_antibodies_by_patient,
        pair_labels=pair_labels,
    )


def _avg_percent(fractions: list[float]) -> str:
    if not fractions:
        return "n/a"
    return f"{sum(fractions) / len(fractions) * 100:.1f}%"


def render_report(pool: SimulatedPool, results: dict) -> str:
    graph = next(iter(results.values())).graph
    index = build_graph_index(graph, pool.patient_antibodies_by_patient)

    lines = [
        "# Exchange matching policy comparison",
        "",
        f"Simulated pool: {len(pool.nodes)} incompatible donor/recipient pairs "
        f"(seed {RANDOM_SEED}). Graph: {len(graph.nodes)} nodes, {len(graph.edges)} "
        "compatible directed edges.",
        "",
        "## Summary",
        "",
        "| Policy | Cycles selected | Pairs transplanted | Total mismatch quality | "
        "Total equity score | Total LKDPI quality |",
        "|---|---|---|---|---|---|",
    ]

    matched_by_policy: dict[str, set[uuid.UUID]] = {}
    for policy_name, result in results.items():
        pairs_transplanted = sum(len(cycle.pair_ids) for cycle in result.selected_cycles)
        quality_total = sum(
            score_cycle(cycle.pair_ids, index, "max_quality") for cycle in result.selected_cycles
        )
        equity_total = sum(
            score_cycle(cycle.pair_ids, index, "equity_weighted")
            for cycle in result.selected_cycles
        )
        lkdpi_total = sum(
            score_cycle(cycle.pair_ids, index, "max_lkdpi_quality")
            for cycle in result.selected_cycles
        )
        matched_by_policy[policy_name] = {
            pair_id for cycle in result.selected_cycles for pair_id in cycle.pair_ids
        }
        lines.append(
            f"| {policy_name} | {len(result.selected_cycles)} | {pairs_transplanted} | "
            f"{quality_total:.1f} | {equity_total:.1f} | {lkdpi_total:.1f} |"
        )

    cpra_by_pair_id = {node.pair_id: cpra_fraction(node.patient.id, index) for node in pool.nodes}

    lines += ["", "## cPRA of matched vs. unmatched patients", ""]
    lines += ["| Policy | Avg cPRA (matched) | Avg cPRA (unmatched) |", "|---|---|---|"]
    for policy_name in results:
        matched_ids = matched_by_policy[policy_name]
        matched_cpra = [cpra_by_pair_id[pid] for pid in cpra_by_pair_id if pid in matched_ids]
        unmatched_cpra = [cpra_by_pair_id[pid] for pid in cpra_by_pair_id if pid not in matched_ids]
        lines.append(
            f"| {policy_name} | {_avg_percent(matched_cpra)} | {_avg_percent(unmatched_cpra)} |"
        )

    lines += ["", "## Which patients each policy transplants", ""]
    all_policies = list(results.keys())
    for policy_name in all_policies:
        lines.append(f"### {policy_name}")
        lines.append("")
        matched_ids = matched_by_policy[policy_name]
        if not matched_ids:
            lines.append("_No pairs matched._")
        else:
            for pair_id in sorted(matched_ids, key=lambda pid: pool.pair_labels[pid]):
                lines.append(f"- {pool.pair_labels[pair_id]}")
        lines.append("")

    only_in = {}
    baseline = "max_transplants"
    for policy_name in all_policies:
        if policy_name == baseline:
            continue
        only_in[policy_name] = matched_by_policy[policy_name] - matched_by_policy[baseline]

    lines += [f"## Patients only {baseline.replace('_', ' ')} misses", ""]
    for policy_name, extra_ids in only_in.items():
        lines.append(f"### Matched by {policy_name} but not {baseline}")
        lines.append("")
        if not extra_ids:
            lines.append("_None -- same patients matched as max_transplants._")
        else:
            for pair_id in sorted(extra_ids, key=lambda pid: pool.pair_labels[pid]):
                lines.append(f"- {pool.pair_labels[pair_id]}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    pool = build_synthetic_pool()
    graph = build_exchange_graph(
        pool.nodes,
        pool.donor_typing_entries_by_donor,
        pool.patient_typing_entries_by_patient,
        pool.patient_antibodies_by_patient,
    )

    results = {
        policy_name: solve_exchange_matching(graph, policy_name, pool.patient_antibodies_by_patient)
        for policy_name in WEIGHT_POLICIES
    }

    report = render_report(pool, results)

    output_dir = Path(__file__).resolve().parent.parent / "research"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "exchange_policy_comparison.md"
    output_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
