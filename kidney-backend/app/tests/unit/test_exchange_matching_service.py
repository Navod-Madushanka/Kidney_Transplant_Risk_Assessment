# app/tests/unit/test_exchange_matching_service.py
"""
Cycle enumeration and the three weight policies, driven off hand-built
ExchangeGraph fixtures (not evaluate_pair_edge output) so each test controls
exactly the mismatch count/edge shape it's about — see
test_exchange_graph_service.py for coverage of the edge-scoring itself.
"""
import itertools
import uuid
from datetime import date, datetime, timezone

import pulp
import pytest

from app.models.donor import Donor
from app.models.enums import BloodType, DonorStatus, RhFactor
from app.models.patient import Patient
from app.services.abo_service import ABOResult
from app.services.dsa_service import DSAResult
from app.services.exchange_graph_service import (
    ExchangeEdge,
    ExchangeGraph,
    ExchangePairNode,
    PairEdgeResult,
)
from unittest.mock import patch

import app.services.exchange_matching_service as exchange_matching_service
from app.services.exchange_matching_service import (
    _canonicalize,
    _wait_fraction,
    build_graph_index,
    cpra_fraction,
    enumerate_cycles,
    solve_exchange_matching,
)
from app.services.hla_mismatch_service import MismatchResult


def _patient() -> Patient:
    return Patient(
        id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        full_name="P",
        date_of_birth=date(1985, 1, 1),
        blood_type=BloodType.O,
        rh_factor=RhFactor.POSITIVE,
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
    )


def _node(patient: Patient | None = None) -> ExchangePairNode:
    donor = Donor(
        id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        full_name="D",
        date_of_birth=date(1990, 1, 1),
        blood_type=BloodType.O,
        rh_factor=RhFactor.POSITIVE,
        status=DonorStatus.AVAILABLE,
        is_deleted=False,
    )
    patient = patient or _patient()
    return ExchangePairNode(
        donor=donor,
        patient=patient,
        donor_hospital_name="H",
        donor_doctor_full_name="Dr",
        donor_doctor_email="dr@example.com",
        patient_hospital_name="H",
        patient_doctor_full_name="Dr",
        patient_doctor_email="dr@example.com",
    )


def _edge(
    from_node: ExchangePairNode, to_node: ExchangePairNode, total_mismatches: int = 0
) -> ExchangeEdge:
    return ExchangeEdge(
        from_pair_id=from_node.pair_id,
        to_pair_id=to_node.pair_id,
        result=PairEdgeResult(
            is_compatible=True,
            abo_result=ABOResult(is_compatible=True, recipient_type="O", donor_type="O"),
            mismatch_result=MismatchResult(
                total_mismatches=total_mismatches, bucket_name="x", is_halted=False
            ),
            dsa_result=DSAResult(is_halted=False, requires_review=False),
        ),
    )


def _naive_enumerate_cycles(graph: ExchangeGraph) -> set:
    """Ground-truth reference: brute-force check every 2- and 3-node
    ordered subset against the edge set, no cleverness. Used to
    differentially test enumerate_cycles's edge-driven rewrite (review #2
    bug 9) against exactly what it replaced -- the original O(n^3)
    all-triples scan -- since the earlier report(?) run of this same
    differential test against 500 random digraphs is exactly the safety
    net a public algorithm rewrite like this needs, not just the small
    hand-built fixtures above."""
    edge_set = {(edge.from_pair_id, edge.to_pair_id) for edge in graph.edges}
    pair_ids = [node.pair_id for node in graph.nodes]

    cycles = set()
    for i, j in itertools.combinations(pair_ids, 2):
        if (i, j) in edge_set and (j, i) in edge_set:
            cycles.add(_canonicalize((i, j)))
    for i, j, k in itertools.permutations(pair_ids, 3):
        if (i, j) in edge_set and (j, k) in edge_set and (k, i) in edge_set:
            cycles.add(_canonicalize((i, j, k)))
    return cycles


class TestEnumerateCyclesDifferential:
    def test_matches_naive_enumeration_on_random_digraphs(self):
        import random

        rng = random.Random(20260809)
        for _ in range(500):
            n = rng.randint(2, 8)
            nodes = [_node() for _ in range(n)]
            pair_ids = [node.pair_id for node in nodes]
            edges = [
                _edge(nodes[a], nodes[b])
                for a in range(n)
                for b in range(n)
                if a != b and rng.random() < 0.3
            ]
            graph = ExchangeGraph(nodes=nodes, edges=edges)

            assert set(enumerate_cycles(graph)) == _naive_enumerate_cycles(graph), (
                f"mismatch for pair_ids={pair_ids}, "
                f"edges={[(e.from_pair_id, e.to_pair_id) for e in edges]}"
            )


class TestEnumerateCycles:
    def test_finds_a_mutual_two_cycle(self):
        a, b = _node(), _node()
        graph = ExchangeGraph(nodes=[a, b], edges=[_edge(a, b), _edge(b, a)])

        cycles = enumerate_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a.pair_id, b.pair_id}

    def test_a_one_directional_edge_is_not_a_cycle(self):
        a, b = _node(), _node()
        graph = ExchangeGraph(nodes=[a, b], edges=[_edge(a, b)])

        assert enumerate_cycles(graph) == []

    def test_finds_a_three_cycle(self):
        a, b, c = _node(), _node(), _node()
        graph = ExchangeGraph(nodes=[a, b, c], edges=[_edge(a, b), _edge(b, c), _edge(c, a)])

        cycles = enumerate_cycles(graph)

        assert len(cycles) == 1
        assert set(cycles[0]) == {a.pair_id, b.pair_id, c.pair_id}


class TestWaitFraction:
    def test_returns_zero_when_created_at_is_none(self):
        # Review #2 bug 18: patient.created_at is a NOT NULL DB column, so
        # this is unreachable through the normal DB-backed code path -- but
        # scripts/tests can hand-build a Patient without it, and this used
        # to raise AttributeError on created_at.tzinfo rather than degrade
        # gracefully.
        patient = _patient()
        patient.created_at = None

        assert _wait_fraction(patient) == 0.0


class TestCpraFractionMemoization:
    def test_repeated_calls_for_the_same_patient_hit_calculate_cpra_once(self):
        # Review #2 bug 19: cpra_fraction used to recompute calculate_cpra
        # (a full population-frequency combination) from scratch on every
        # call, even for the same patient across multiple candidate cycles
        # in one solve.
        node = _node()
        graph = ExchangeGraph(nodes=[node], edges=[])
        index = build_graph_index(graph, {node.patient.id: []})

        with patch(
            "app.services.exchange_matching_service.calculate_cpra",
            wraps=exchange_matching_service.calculate_cpra,
        ) as mock_calculate_cpra:
            cpra_fraction(node.patient.id, index)
            cpra_fraction(node.patient.id, index)
            cpra_fraction(node.patient.id, index)

        assert mock_calculate_cpra.call_count == 1


class TestSolveExchangeMatching:
    def test_max_transplants_prefers_the_larger_cycle_when_they_conflict(self):
        a, b, c = _node(), _node(), _node()
        edges = [_edge(a, b), _edge(b, a), _edge(b, c), _edge(c, a)]
        graph = ExchangeGraph(nodes=[a, b, c], edges=edges)

        result = solve_exchange_matching(graph, "max_transplants")

        assert len(result.selected_cycles) == 1
        assert set(result.selected_cycles[0].pair_ids) == {a.pair_id, b.pair_id, c.pair_id}

    def test_max_quality_prefers_the_better_matched_cycle_even_if_smaller(self):
        a, b, c = _node(), _node(), _node()
        edges = [
            _edge(a, b, total_mismatches=0),
            _edge(b, a, total_mismatches=0),
            _edge(b, c, total_mismatches=5),
            _edge(c, a, total_mismatches=5),
        ]
        graph = ExchangeGraph(nodes=[a, b, c], edges=edges)

        result = solve_exchange_matching(graph, "max_quality")

        assert len(result.selected_cycles) == 1
        assert set(result.selected_cycles[0].pair_ids) == {a.pair_id, b.pair_id}

    def test_disjoint_cycles_are_both_selected(self):
        a, b, c, d = _node(), _node(), _node(), _node()
        edges = [_edge(a, b), _edge(b, a), _edge(c, d), _edge(d, c)]
        graph = ExchangeGraph(nodes=[a, b, c, d], edges=edges)

        result = solve_exchange_matching(graph, "max_transplants")

        selected_pairs = {frozenset(cycle.pair_ids) for cycle in result.selected_cycles}
        assert selected_pairs == {
            frozenset([a.pair_id, b.pair_id]),
            frozenset([c.pair_id, d.pair_id]),
        }

    def test_equity_weighted_runs_end_to_end_without_antibody_data(self):
        a, b = _node(), _node()
        graph = ExchangeGraph(nodes=[a, b], edges=[_edge(a, b), _edge(b, a)])

        result = solve_exchange_matching(graph, "equity_weighted")

        assert len(result.selected_cycles) == 1

    def test_one_patient_with_two_donors_is_not_selected_in_two_cycles(self):
        # Regression coverage for review #2 bug 4: a patient with two
        # candidate donors is two separate pool nodes (pair_id is the
        # donor's id -- see ExchangePairNode's docstring), and only the
        # pair-level disjointness constraint used to exist. Here patient P
        # has donors a1 and a2, each independently forming a mutual
        # 2-cycle with a different partner (b, c) -- without the
        # patient-level constraint, max_transplants would happily select
        # both cycles and transplant P twice.
        shared_patient = _patient()
        a1, a2 = _node(shared_patient), _node(shared_patient)
        b, c = _node(), _node()
        edges = [_edge(a1, b), _edge(b, a1), _edge(a2, c), _edge(c, a2)]
        graph = ExchangeGraph(nodes=[a1, a2, b, c], edges=edges)

        result = solve_exchange_matching(graph, "max_transplants")

        selected_pairs = {pid for cycle in result.selected_cycles for pid in cycle.pair_ids}
        assert len(result.selected_cycles) == 1
        assert len({a1.pair_id, a2.pair_id} & selected_pairs) == 1

    def test_non_optimal_solve_raises_instead_of_a_silent_empty_result(self, monkeypatch):
        # Review #2 bug 8: a non-Optimal solve (Infeasible/Not Solved) used
        # to render identically to a genuine "no cycles found" -- every
        # var.value() comes back None, `None == 1` is False, nothing
        # errors. Simulated here since this formulation's trivial
        # all-zero solution is always feasible in practice, so a real
        # Infeasible run can't be constructed from ordinary inputs.
        def fake_solve(self, *args, **kwargs):
            self.status = pulp.LpStatusInfeasible
            return pulp.LpStatusInfeasible

        monkeypatch.setattr(pulp.LpProblem, "solve", fake_solve)

        a, b = _node(), _node()
        graph = ExchangeGraph(nodes=[a, b], edges=[_edge(a, b), _edge(b, a)])

        with pytest.raises(RuntimeError, match="Infeasible"):
            solve_exchange_matching(graph, "max_transplants")

    def test_unknown_policy_raises(self):
        graph = ExchangeGraph(nodes=[], edges=[])

        with pytest.raises(ValueError):
            solve_exchange_matching(graph, "not_a_real_policy")

    def test_empty_graph_returns_no_cycles(self):
        graph = ExchangeGraph(nodes=[], edges=[])

        result = solve_exchange_matching(graph, "max_transplants")

        assert result.selected_cycles == []
