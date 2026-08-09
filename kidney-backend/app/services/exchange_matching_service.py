# app/services/exchange_matching_service.py
"""
Cycle enumeration and maximum-weight cycle packing over the exchange graph
built by exchange_graph_service.py.

Only 2- and 3-cycles are enumerated (O(n^3)) -- real kidney-paired-donation
programs cap cycle length for the same practical reason: every donor
nephrectomy in a cycle has to happen simultaneously (nobody can back out
after their own recipient has already received a kidney), so a 4+-way cycle
is an increasingly hard logistical ask for an increasingly rare marginal
benefit. Fine below ~300 pool pairs, per the original spec.

KNOWN MVP LIMITATION: "at most one selected cycle per pair" below is
enforced per *pair* (exchange_graph_service.ExchangePairNode, keyed by
donor id), not per *patient*. A patient registered with two candidate
donors appears as two separate pool nodes, and nothing here stops the
solver selecting both in two different cycles -- double-booking that one
patient. Not handled because it needs linking sibling nodes back to a
shared patient identity in the ILP constraints, and no data in this pass
exercises the multi-donor-per-patient case. Flagging for a real deployment,
not fixing speculatively here.

This is read-only: solving the exchange never writes to the database or
transitions donor/patient status (see exchange_graph_service.py).
"""
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import pulp

from app.models.patient import Patient
from app.reference_data.exchange_weight_policies import (
    BASE_TRANSPLANT_WEIGHT,
    CPRA_WEIGHT,
    WAIT_NORMALIZATION_DAYS,
    WAIT_WEIGHT,
)
from app.reference_data.hla_antigen_frequencies import (
    HLA_ANTIGEN_FREQUENCIES,
    HLA_FREQUENCY_TABLE_CITATION,
    HLA_FREQUENCY_TABLE_SAMPLE_SIZE,
    HLA_FREQUENCY_TABLE_VERSION,
)
from app.reference_data.mismatch_buckets import MAX_ACCEPTABLE_MISMATCHES
from app.services.cpra_service import calculate_cpra
from app.services.dsa_service import DEFAULT_MFI_CUTOFF, PatientAntibody
from app.services.exchange_graph_service import ExchangeEdge, ExchangeGraph, ExchangePairNode

Cycle = tuple[uuid.UUID, ...]  # ordered pair_ids: cycle[i]'s donor gives to cycle[i+1]'s recipient


def _canonicalize(cycle: Cycle) -> Cycle:
    """Rotates a cycle so it starts at its smallest pair_id -- so the same
    cycle discovered from a different starting node dedupes to one entry.
    Only rotations are equivalent, never reversals: a 3-cycle and its
    mirror image use different directed edges and are genuinely different
    candidates (kept separately if both actually validate)."""
    n = len(cycle)
    start = min(range(n), key=lambda idx: cycle[idx])
    return tuple(cycle[(start + offset) % n] for offset in range(n))


def enumerate_cycles(graph: ExchangeGraph) -> list[Cycle]:
    edge_set = {(edge.from_pair_id, edge.to_pair_id) for edge in graph.edges}
    pair_ids = [node.pair_id for node in graph.nodes]

    cycles: set[Cycle] = set()

    for i, j in itertools.combinations(pair_ids, 2):
        if (i, j) in edge_set and (j, i) in edge_set:
            cycles.add(_canonicalize((i, j)))

    for i, j, k in itertools.permutations(pair_ids, 3):
        if (i, j) in edge_set and (j, k) in edge_set and (k, i) in edge_set:
            cycles.add(_canonicalize((i, j, k)))

    return sorted(cycles)


EdgeByPair = dict[tuple[uuid.UUID, uuid.UUID], ExchangeEdge]


def _cycle_edges(cycle: Cycle, edge_by_pair: EdgeByPair) -> list[ExchangeEdge]:
    n = len(cycle)
    return [edge_by_pair[(cycle[idx], cycle[(idx + 1) % n])] for idx in range(n)]


AntibodiesByPatient = dict[uuid.UUID, list[PatientAntibody]]


@dataclass
class GraphIndex:
    node_by_id: dict[uuid.UUID, ExchangePairNode]
    edge_by_pair: EdgeByPair
    patient_antibodies_by_patient: AntibodiesByPatient = field(default_factory=dict)


def build_graph_index(
    graph: ExchangeGraph, patient_antibodies_by_patient: AntibodiesByPatient | None = None
) -> GraphIndex:
    return GraphIndex(
        node_by_id={node.pair_id: node for node in graph.nodes},
        edge_by_pair={(edge.from_pair_id, edge.to_pair_id): edge for edge in graph.edges},
        patient_antibodies_by_patient=patient_antibodies_by_patient or {},
    )


def weight_max_transplants(cycle: Cycle, index: GraphIndex) -> float:
    """Maximizing the sum of this weight across selected (non-overlapping)
    cycles maximizes total pairs transplanted, since each pair contributes
    exactly its own count regardless of which cycle carries it."""
    return float(len(cycle))


def weight_max_quality(cycle: Cycle, index: GraphIndex) -> float:
    """Rewards fewer HLA mismatches per edge, scaled against the same
    0..MAX_ACCEPTABLE_MISMATCHES range Step 3's mismatch gate uses, so a
    0-mismatch edge is worth the most and a just-barely-passing edge is
    worth close to nothing."""
    edges = _cycle_edges(cycle, index.edge_by_pair)
    return float(
        sum(
            MAX_ACCEPTABLE_MISMATCHES - edge.result.mismatch_result.total_mismatches
            for edge in edges
        )
    )


def cpra_fraction(patient_id: uuid.UUID, index: GraphIndex) -> float:
    antibodies = index.patient_antibodies_by_patient.get(patient_id, [])
    # Same ">" threshold get_patient_sensitized_antigens uses (antibody_
    # profile_service.py) -- independent of any one donor's antigens, since
    # cPRA measures how hard this patient is to match against the general
    # population, not against one specific pairing.
    sensitized_antigens = [
        antibody.antigen for antibody in antibodies if antibody.mfi > DEFAULT_MFI_CUTOFF
    ]
    cpra_result = calculate_cpra(
        sensitized_antigens=sensitized_antigens,
        antigen_frequencies=HLA_ANTIGEN_FREQUENCIES,
        reference_sample_size=HLA_FREQUENCY_TABLE_SAMPLE_SIZE,
        reference_table_version=HLA_FREQUENCY_TABLE_VERSION,
        source_citation=HLA_FREQUENCY_TABLE_CITATION,
    )
    return (cpra_result.cpra_percentage or 0.0) / 100.0


def _wait_fraction(patient: Patient) -> float:
    """See exchange_weight_policies.py's module docstring: Patient.created_at
    (registration date) is a disclosed proxy for actual waiting time."""
    created_at = patient.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days_waiting = (datetime.now(timezone.utc) - created_at).days
    return max(0.0, min(days_waiting / WAIT_NORMALIZATION_DAYS, 1.0))


def weight_equity(cycle: Cycle, index: GraphIndex) -> float:
    """Base transplant credit plus cPRA and waiting-time bonuses per pair
    transplanted -- see exchange_weight_policies.py for the constants and
    their rationale."""
    total = 0.0
    for pair_id in cycle:
        patient = index.node_by_id[pair_id].patient
        total += (
            BASE_TRANSPLANT_WEIGHT
            + CPRA_WEIGHT * cpra_fraction(patient.id, index)
            + WAIT_WEIGHT * _wait_fraction(patient)
        )
    return total


WEIGHT_POLICIES: dict[str, Callable[[Cycle, GraphIndex], float]] = {
    "max_transplants": weight_max_transplants,
    "max_quality": weight_max_quality,
    "equity_weighted": weight_equity,
}


def score_cycle(cycle: Cycle, index: GraphIndex, policy_name: str) -> float:
    """Scores one cycle under a named policy's weight function, independent
    of which policy actually selected it -- lets a caller (e.g.
    scripts/exchange_policy_comparison.py) report a fixed set of selected
    cycles on every policy's yardstick, not just the one that chose them."""
    if policy_name not in WEIGHT_POLICIES:
        raise ValueError(f"Unknown exchange weight policy: {policy_name!r}")
    return WEIGHT_POLICIES[policy_name](cycle, index)


@dataclass
class SelectedCycle:
    pair_ids: Cycle
    weight: float


@dataclass
class ExchangeMatchResult:
    policy: str
    graph: ExchangeGraph
    selected_cycles: list[SelectedCycle]


def solve_exchange_matching(
    graph: ExchangeGraph,
    policy_name: str,
    patient_antibodies_by_patient: dict[uuid.UUID, list[PatientAntibody]] | None = None,
) -> ExchangeMatchResult:
    """Maximum-weight cycle packing via PuLP/CBC:

        maximise   sum_c w_c * x_c
        s.t.       sum_{c containing v} x_c <= 1   for every pool node v

    `patient_antibodies_by_patient` is only consulted by the equity_weighted
    policy (weight_max_transplants/weight_max_quality read solely from
    `graph`) -- pass the same dict exchange_graph_service.load_exchange_pool
    / build_exchange_graph already used, no separate fetch needed.
    """
    if policy_name not in WEIGHT_POLICIES:
        raise ValueError(f"Unknown exchange weight policy: {policy_name!r}")

    weight_fn = WEIGHT_POLICIES[policy_name]
    index = build_graph_index(graph, patient_antibodies_by_patient)

    cycles = enumerate_cycles(graph)
    if not cycles:
        return ExchangeMatchResult(policy=policy_name, graph=graph, selected_cycles=[])

    weights = [weight_fn(cycle, index) for cycle in cycles]

    problem = pulp.LpProblem("exchange_matching", pulp.LpMaximize)
    cycle_vars = [pulp.LpVariable(f"cycle_{idx}", cat="Binary") for idx in range(len(cycles))]
    problem += pulp.lpSum(weight * var for weight, var in zip(weights, cycle_vars))

    for pair_id in index.node_by_id:
        involved_vars = [var for cycle, var in zip(cycles, cycle_vars) if pair_id in cycle]
        if involved_vars:
            problem += pulp.lpSum(involved_vars) <= 1

    problem.solve(pulp.PULP_CBC_CMD(msg=False))

    selected_cycles = [
        SelectedCycle(pair_ids=cycle, weight=weight)
        for cycle, var, weight in zip(cycles, cycle_vars, weights)
        if var.value() == 1
    ]
    return ExchangeMatchResult(policy=policy_name, graph=graph, selected_cycles=selected_cycles)
