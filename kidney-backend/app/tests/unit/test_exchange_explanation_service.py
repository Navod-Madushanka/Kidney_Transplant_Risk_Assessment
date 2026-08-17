# app/tests/unit/test_exchange_explanation_service.py
"""
K7: compute_pair_match_explanations, driven off hand-built ExchangeGraph/
Cycle/SelectedCycle fixtures (same style test_exchange_matching_service.py
uses) so each test controls exactly the edge/cycle shape its verdict needs,
without going through evaluate_pair_edge or the CBC solver.
"""
import uuid
from datetime import date, datetime, timezone

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
from app.services.exchange_explanation_service import compute_pair_match_explanations
from app.services.exchange_matching_service import SelectedCycle
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


def _edge(from_node: ExchangePairNode, to_node: ExchangePairNode) -> ExchangeEdge:
    return ExchangeEdge(
        from_pair_id=from_node.pair_id,
        to_pair_id=to_node.pair_id,
        result=PairEdgeResult(
            is_compatible=True,
            abo_result=ABOResult(is_compatible=True, recipient_type="O", donor_type="O"),
            mismatch_result=MismatchResult(total_mismatches=0, bucket_name="x", is_halted=False),
            dsa_result=DSAResult(is_halted=False, requires_review=False),
        ),
    )


class TestComputePairMatchExplanations:
    def test_all_four_verdicts_in_one_pool(self):
        # no_donor_out: zero outbound edges, even though it has an inbound one.
        p_out = _node()
        inbound_source = _node()

        # no_donor_in: an outbound edge, but nothing points back at it.
        p_in = _node()
        outbound_target = _node()

        # no_reciprocal_path: both an outbound and an inbound edge, but they
        # don't close into any 2-/3-cycle.
        p_iso = _node()
        iso_target = _node()
        iso_source = _node()

        # lost_to_overlap: q1<->q3 is a real candidate 2-cycle, but the
        # solver picked the overlapping q1<->q2 cycle instead.
        q1, q2, q3 = _node(), _node(), _node()

        nodes = [
            p_out, inbound_source, p_in, outbound_target, p_iso, iso_target,
            iso_source, q1, q2, q3,
        ]
        edges = [
            _edge(inbound_source, p_out),
            _edge(p_in, outbound_target),
            _edge(p_iso, iso_target),
            _edge(iso_source, p_iso),
            _edge(q1, q2),
            _edge(q2, q1),
            _edge(q1, q3),
            _edge(q3, q1),
        ]
        graph = ExchangeGraph(nodes=nodes, edges=edges)

        cycles = [(q1.pair_id, q2.pair_id), (q1.pair_id, q3.pair_id)]
        selected_cycles = [SelectedCycle(pair_ids=(q1.pair_id, q2.pair_id), weight=2.0)]

        explanations = compute_pair_match_explanations(graph, cycles, selected_cycles)
        by_pair_id = {explanation.pair_id: explanation for explanation in explanations}

        # q1 and q2 are matched -- no explanation for either.
        assert q1.pair_id not in by_pair_id
        assert q2.pair_id not in by_pair_id

        assert by_pair_id[p_out.pair_id].verdict == "no_donor_out"
        assert by_pair_id[p_out.pair_id].outbound_edges == 0
        assert by_pair_id[p_out.pair_id].inbound_edges == 1

        assert by_pair_id[p_in.pair_id].verdict == "no_donor_in"
        assert by_pair_id[p_in.pair_id].outbound_edges == 1
        assert by_pair_id[p_in.pair_id].inbound_edges == 0

        assert by_pair_id[p_iso.pair_id].verdict == "no_reciprocal_path"
        assert by_pair_id[p_iso.pair_id].outbound_edges == 1
        assert by_pair_id[p_iso.pair_id].inbound_edges == 1
        assert by_pair_id[p_iso.pair_id].candidate_cycles == 0

        assert by_pair_id[q3.pair_id].verdict == "lost_to_overlap"
        assert by_pair_id[q3.pair_id].candidate_cycles == 1

    def test_rejection_reasons_are_tallied_on_the_graph_and_surfaced(self):
        donor_incompatible = _node()
        target = _node()
        graph = ExchangeGraph(
            nodes=[donor_incompatible, target],
            edges=[],
            outbound_blocked={donor_incompatible.pair_id: {"abo": 1}},
            inbound_blocked={target.pair_id: {"abo": 1}},
        )

        explanations = compute_pair_match_explanations(graph, cycles=[], selected_cycles=[])
        by_pair_id = {explanation.pair_id: explanation for explanation in explanations}

        assert by_pair_id[donor_incompatible.pair_id].outbound_blocked == {"abo": 1}
        assert by_pair_id[target.pair_id].inbound_blocked == {"abo": 1}
