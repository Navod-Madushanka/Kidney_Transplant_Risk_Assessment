# app/services/exchange_explanation_service.py
"""
"Why wasn't this pair matched?" -- the K7 decision-support addition. Answers
the most common coordinator question with data the exchange engine already
computes and previously threw away: exchange_graph_service.build_exchange_graph
scores every ordered pair in the pool (O(n^2)) and exchange_matching_service
.enumerate_cycles finds every candidate 2-/3-cycle, but until now only the
selected cycles ever reached the API response.

Deliberately aggregate-only, never the n^2 detail: at a 300-pair pool that
would be 90,000 individual results. Only a handful of counts per pool pair
survive here (see PairMatchExplanation), and only for pairs that aren't in
any selected cycle -- a matched pair doesn't need an explanation.
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from app.services.exchange_graph_service import ExchangeGraph
from app.services.exchange_matching_service import Cycle, SelectedCycle

# Priority order matters: a pair can satisfy more than one condition at once
# (e.g. zero outbound edges AND zero inbound edges), and only the first
# applicable verdict is reported, per the decision-support spec.
_NO_DONOR_OUT = "no_donor_out"
_NO_DONOR_IN = "no_donor_in"
_NO_RECIPROCAL_PATH = "no_reciprocal_path"
_LOST_TO_OVERLAP = "lost_to_overlap"


@dataclass(frozen=True)
class PairMatchExplanation:
    pair_id: uuid.UUID
    outbound_blocked: dict[str, int] = field(default_factory=dict)
    inbound_blocked: dict[str, int] = field(default_factory=dict)
    outbound_edges: int = 0
    inbound_edges: int = 0
    candidate_cycles: int = 0
    verdict: str = _NO_DONOR_OUT


def compute_pair_match_explanations(
    graph: ExchangeGraph,
    cycles: list[Cycle],
    selected_cycles: list[SelectedCycle],
) -> list[PairMatchExplanation]:
    """One PairMatchExplanation per pool pair that ISN'T in any selected
    cycle. `cycles` is every candidate 2-/3-cycle enumerate_cycles found
    (ExchangeMatchResult.cycles) -- reused here rather than re-enumerated,
    since cycle enumeration is part of a solve's expensive fixed cost."""
    selected_pair_ids = {
        pair_id for selected in selected_cycles for pair_id in selected.pair_ids
    }

    outbound_edge_count: dict[uuid.UUID, int] = defaultdict(int)
    inbound_edge_count: dict[uuid.UUID, int] = defaultdict(int)
    for edge in graph.edges:
        outbound_edge_count[edge.from_pair_id] += 1
        inbound_edge_count[edge.to_pair_id] += 1

    candidate_cycle_count: dict[uuid.UUID, int] = defaultdict(int)
    for cycle in cycles:
        for pair_id in cycle:
            candidate_cycle_count[pair_id] += 1

    explanations: list[PairMatchExplanation] = []
    for node in graph.nodes:
        pair_id = node.pair_id
        if pair_id in selected_pair_ids:
            continue

        outbound_edges = outbound_edge_count.get(pair_id, 0)
        inbound_edges = inbound_edge_count.get(pair_id, 0)
        candidate_cycles = candidate_cycle_count.get(pair_id, 0)

        if outbound_edges == 0:
            verdict = _NO_DONOR_OUT
        elif inbound_edges == 0:
            verdict = _NO_DONOR_IN
        elif candidate_cycles == 0:
            verdict = _NO_RECIPROCAL_PATH
        else:
            verdict = _LOST_TO_OVERLAP

        explanations.append(
            PairMatchExplanation(
                pair_id=pair_id,
                outbound_blocked=graph.outbound_blocked.get(pair_id, {}),
                inbound_blocked=graph.inbound_blocked.get(pair_id, {}),
                outbound_edges=outbound_edges,
                inbound_edges=inbound_edges,
                candidate_cycles=candidate_cycles,
                verdict=verdict,
            )
        )

    return explanations
