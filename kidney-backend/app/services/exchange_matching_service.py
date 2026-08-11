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

Two disjointness constraints keep a selection valid: at most one selected
cycle per *pair* (exchange_graph_service.ExchangePairNode, keyed by donor
id) AND at most one selected cycle per *patient* -- the latter closes what
was previously a known gap (review #2 bug 4): a patient registered with two
candidate donors appears as two separate pool nodes, and without the
patient-level constraint the solver could select both in two different
cycles, giving that one patient two simultaneous transplants.

This is read-only: solving the exchange never writes to the database or
transitions donor/patient status (see exchange_graph_service.py).
"""
import itertools
import uuid
from collections import defaultdict
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
    """Only 2- and 3-cycles (see module docstring for why). The 3-cycle
    search is edge-driven (review #2 bug 9), not the O(n^3) all-triples
    scan it used to be: for every real edge i->j, only j's actual
    out-neighbors k are considered (not every other node in the graph),
    and (k, i) is a single O(1) set lookup -- O(|E|*d) where d is the
    graph's max out-degree, instead of always paying n^3 regardless of
    how sparse the graph actually is. 6x redundant work is also gone:
    the old version tested all 6 permutations of every 3-node subset and
    let `cycles.add(_canonicalize(...))`'s set-dedup quietly absorb the
    waste; this version only ever discovers each 3-cycle from its edges
    once per rotation (3 times, same as the old version's `cycles` set
    still needs the same _canonicalize() collapse for -- see
    _canonicalize's own docstring), not 6."""
    edge_set = {(edge.from_pair_id, edge.to_pair_id) for edge in graph.edges}
    pair_ids = [node.pair_id for node in graph.nodes]

    out_neighbors: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for edge in graph.edges:
        out_neighbors[edge.from_pair_id].append(edge.to_pair_id)

    cycles: set[Cycle] = set()

    for i, j in itertools.combinations(pair_ids, 2):
        if (i, j) in edge_set and (j, i) in edge_set:
            cycles.add(_canonicalize((i, j)))

    for i, j in edge_set:
        for k in out_neighbors[j]:
            if k != i and (k, i) in edge_set:
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
    # Memoizes cpra_fraction per patient_id (review #2 bug 19) -- lives on
    # GraphIndex itself, not threaded as an extra function parameter, so
    # every WEIGHT_POLICIES entry keeps the exact same
    # Callable[[Cycle, GraphIndex], float] signature regardless of whether
    # its weight function happens to use the cache.
    _cpra_fraction_cache: dict[uuid.UUID, float] = field(default_factory=dict)


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


def weight_max_lkdpi_quality(cycle: Cycle, index: GraphIndex) -> float:
    """Rewards a lower LKDPI (see app/services/lkdpi_service.py) per edge --
    Sigma(100 - LKDPI), floored at 0 per edge so an unusually high LKDPI on
    one edge can't push the whole cycle's weight negative and make "no
    cycle" look better than "one bad-but-real cycle". An edge whose LKDPI
    couldn't be computed (missing donor/recipient inputs -- weight, sex,
    biological relationship, etc.) contributes 0, the same treatment a
    maximally-poor LKDPI would get once floored -- this policy simply has
    no opinion on an edge it can't score, rather than guessing one.
    """
    edges = _cycle_edges(cycle, index.edge_by_pair)
    total = 0.0
    for edge in edges:
        lkdpi_result = edge.result.lkdpi_result
        if lkdpi_result is None or lkdpi_result.score is None:
            continue
        total += max(0.0, 100.0 - lkdpi_result.score)
    return total


def cpra_fraction(patient_id: uuid.UUID, index: GraphIndex) -> float:
    """Memoized per patient_id via index._cpra_fraction_cache (review #2
    bug 19): calculate_cpra does a full population-frequency combination
    over a patient's sensitized antigens, and the same patient can appear
    in many candidate cycles (2- and 3-cycles alike) -- without this, an
    equity_weighted solve recomputed the identical result from scratch
    once per cycle the patient appeared in, not once per patient."""
    if patient_id in index._cpra_fraction_cache:
        return index._cpra_fraction_cache[patient_id]

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
    fraction = (cpra_result.cpra_percentage or 0.0) / 100.0
    index._cpra_fraction_cache[patient_id] = fraction
    return fraction


def _wait_fraction(patient: Patient) -> float:
    """See exchange_weight_policies.py's module docstring: Patient.created_at
    (registration date) is a disclosed proxy for actual waiting time.
    created_at is a NOT NULL DB column, so this is unreachable through the
    normal DB-backed code path -- the guard (review #2 bug 18) is for
    synthetic/hand-built Patient objects (scripts, tests) that can leave it
    unset, which is exactly how this was originally found."""
    created_at = patient.created_at
    if created_at is None:
        return 0.0
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
    "max_lkdpi_quality": weight_max_lkdpi_quality,
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

    # Patient-level disjointness (review #2 bug 4): a pair-level constraint
    # alone doesn't stop one *patient* with two candidate donors (two pool
    # nodes) from being selected in two different cycles at once. Group by
    # the *set* of distinct patients each cycle actually involves (a
    # dedupe, not just a list) since a cycle could in principle touch the
    # same patient via two different pair nodes.
    cycles_by_patient: dict[uuid.UUID, list[pulp.LpVariable]] = defaultdict(list)
    for cycle, var in zip(cycles, cycle_vars):
        patient_ids = {index.node_by_id[pair_id].patient.id for pair_id in cycle}
        for patient_id in patient_ids:
            cycles_by_patient[patient_id].append(var)
    for involved_vars in cycles_by_patient.values():
        if len(involved_vars) > 1:
            problem += pulp.lpSum(involved_vars) <= 1

    problem.solve(pulp.PULP_CBC_CMD(msg=False))

    # Review #2 bug 8: `problem.solve()`'s return status was never checked
    # -- an Infeasible/Not Solved CBC run used to render identically to a
    # genuine "no cycles found" result (every var.value() comes back None,
    # and `None == 1` is just False, so nothing errors, it just silently
    # under-reports). Raising here turns a solver failure into a visible
    # 500 instead of a confident-looking empty match.
    solve_status = pulp.LpStatus[problem.status]
    if solve_status != "Optimal":
        raise RuntimeError(
            f"Exchange matching solve did not reach an optimal solution "
            f"(status: {solve_status!r}, policy: {policy_name!r}, "
            f"{len(cycles)} candidate cycles)."
        )

    selected_cycles = [
        SelectedCycle(pair_ids=cycle, weight=weight)
        for cycle, var, weight in zip(cycles, cycle_vars, weights)
        # Exact `== 1` used to silently drop any tolerance-level solver
        # output (e.g. 0.9999999999, or 1.0000000001) as "not selected" --
        # CBC's solutions for a binary MILP are numerically exact in
        # practice, but treating anything within simplex/MILP tolerance of
        # 1 as selected is the correct comparison regardless.
        if var.value() is not None and var.value() > 0.5
    ]
    return ExchangeMatchResult(policy=policy_name, graph=graph, selected_cycles=selected_cycles)
