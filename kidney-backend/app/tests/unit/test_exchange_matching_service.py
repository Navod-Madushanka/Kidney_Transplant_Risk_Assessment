# app/tests/unit/test_exchange_matching_service.py
"""
Cycle enumeration and the three weight policies, driven off hand-built
ExchangeGraph fixtures (not evaluate_pair_edge output) so each test controls
exactly the mismatch count/edge shape it's about — see
test_exchange_graph_service.py for coverage of the edge-scoring itself.
"""
import uuid
from datetime import date, datetime, timezone

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
from app.services.exchange_matching_service import enumerate_cycles, solve_exchange_matching
from app.services.hla_mismatch_service import MismatchResult


def _node() -> ExchangePairNode:
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
    patient = Patient(
        id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        full_name="P",
        date_of_birth=date(1985, 1, 1),
        blood_type=BloodType.O,
        rh_factor=RhFactor.POSITIVE,
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
    )
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

    def test_unknown_policy_raises(self):
        graph = ExchangeGraph(nodes=[], edges=[])

        with pytest.raises(ValueError):
            solve_exchange_matching(graph, "not_a_real_policy")

    def test_empty_graph_returns_no_cycles(self):
        graph = ExchangeGraph(nodes=[], edges=[])

        result = solve_exchange_matching(graph, "max_transplants")

        assert result.selected_cycles == []
