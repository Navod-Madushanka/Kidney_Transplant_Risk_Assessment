# app/tests/unit/test_exchange_graph_service.py
"""
DB-free coverage for exchange_graph_service.py's pure half: evaluate_pair_edge
(the single-edge scoring function) and build_exchange_graph (the O(n^2)
pairwise assembly). The DB-facing half (load_exchange_pool) is covered at
the HTTP layer in app/tests/integration/test_exchange_api.py, same split
donor_search_service's own test suite uses.
"""
import uuid
from datetime import date

from app.models.donor import Donor
from app.models.donor_hla_typing import DonorHLATyping
from app.models.enums import BloodType, DonorStatus, HLALocusEnum, RhFactor
from app.models.patient import Patient
from app.models.patient_hla_typing import PatientHLATyping
from app.services.dsa_service import PatientAntibody
from app.services.exchange_graph_service import (
    ExchangePairNode,
    build_exchange_graph,
    evaluate_pair_edge,
)

# Identical A/B/DRB1 typing reused on both sides of every "matching" fixture
# below, so calculate_mismatch_result always sees a clean 0-mismatch pairing
# and the tests are free to vary just the one thing (blood type, antibodies)
# they're actually about.
MATCHING_TYPING = [("A", "01", "02"), ("B", "07", "08"), ("DRB1", "03", "04")]


def _typing_dict() -> dict[str, list[str]]:
    return {locus: [a1, a2] for locus, a1, a2 in MATCHING_TYPING}


def _donor_typing_rows(donor_id: uuid.UUID) -> list[DonorHLATyping]:
    return [
        DonorHLATyping(donor_id=donor_id, locus=HLALocusEnum(locus), allele_1=a1, allele_2=a2)
        for locus, a1, a2 in MATCHING_TYPING
    ]


def _patient_typing_rows(patient_id: uuid.UUID) -> list[PatientHLATyping]:
    return [
        PatientHLATyping(patient_id=patient_id, locus=HLALocusEnum(locus), allele_1=a1, allele_2=a2)
        for locus, a1, a2 in MATCHING_TYPING
    ]


def _make_donor(blood_type: BloodType) -> Donor:
    return Donor(
        id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        full_name="Test Donor",
        date_of_birth=date(1990, 1, 1),
        blood_type=blood_type,
        rh_factor=RhFactor.POSITIVE,
        status=DonorStatus.AVAILABLE,
        is_deleted=False,
        hla_typing_verified=True,
    )


def _make_patient(blood_type: BloodType) -> Patient:
    return Patient(
        id=uuid.uuid4(),
        doctor_id=uuid.uuid4(),
        full_name="Test Patient",
        date_of_birth=date(1985, 1, 1),
        blood_type=blood_type,
        rh_factor=RhFactor.POSITIVE,
        is_deleted=False,
        hla_typing_verified=True,
        antibody_profile_verified=True,
    )


def _make_node(donor: Donor, patient: Patient) -> ExchangePairNode:
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


class TestEvaluatePairEdge:
    def test_compatible_pair_with_matching_typing_and_no_antibodies(self):
        result = evaluate_pair_edge(
            patient_typing=_typing_dict(),
            donor_typing=_typing_dict(),
            patient_antibodies=[],
            donor_hla_antigens=["B7", "B8", "DR3", "DR4"],
            patient_blood_type="A",
            donor_blood_type="O",
        )

        assert result.is_compatible is True
        assert result.mismatch_result.total_mismatches == 0
        assert result.dsa_result.is_halted is False

    def test_abo_incompatible_pair_is_not_compatible_regardless_of_hla(self):
        result = evaluate_pair_edge(
            patient_typing=_typing_dict(),
            donor_typing=_typing_dict(),
            patient_antibodies=[],
            donor_hla_antigens=[],
            patient_blood_type="A",
            donor_blood_type="B",
        )

        assert result.abo_result.is_compatible is False
        assert result.is_compatible is False

    def test_strong_dsa_halts_an_otherwise_compatible_pair(self):
        result = evaluate_pair_edge(
            patient_typing=_typing_dict(),
            donor_typing=_typing_dict(),
            patient_antibodies=[PatientAntibody(antigen="B7", mfi=6000.0)],
            donor_hla_antigens=["B7"],
            patient_blood_type="AB",
            donor_blood_type="O",
        )

        assert result.dsa_result.is_halted is True
        assert result.is_compatible is False

    def test_untyped_locus_antibody_only_flagged_when_donor_typed_loci_passed(self):
        # N1 regression: the same clinical inputs must produce the same
        # answer whether they arrive through evaluate_pair_edge directly
        # (the exchange path) or through match_pipeline.py's Step 5 call --
        # both pass donor_typed_loci, so both must set requires_review for
        # an antibody against a locus the donor was never typed for.
        common_kwargs = dict(
            patient_typing=_typing_dict(),
            donor_typing=_typing_dict(),
            patient_antibodies=[PatientAntibody(antigen="DQ7", mfi=9000.0)],
            donor_hla_antigens=["B7", "B8", "DR3", "DR4"],
            patient_blood_type="O",
            donor_blood_type="O",
        )

        without_typed_loci = evaluate_pair_edge(**common_kwargs)
        with_typed_loci = evaluate_pair_edge(**common_kwargs, donor_typed_loci={"A", "B", "DRB1"})

        assert without_typed_loci.dsa_result.requires_review is False
        assert without_typed_loci.dsa_result.untyped_locus_antibodies == []

        assert with_typed_loci.dsa_result.requires_review is True
        assert [a.antigen for a in with_typed_loci.dsa_result.untyped_locus_antibodies] == ["DQ7"]

        # Neither reading halts the edge -- the antibody was never matched
        # against the donor's typing, so nothing here should block a swap
        # outright; it should only surface for review.
        assert without_typed_loci.is_compatible is True
        assert with_typed_loci.is_compatible is True


class TestBuildExchangeGraph:
    def test_two_incompatible_pairs_that_cross_match_form_mutual_edges(self):
        # A-recipient/B-donor and B-recipient/A-donor: each direct pairing
        # would be ABO-incompatible on its own, but swapped they both work
        # (A accepts A/O, B accepts B/O) -- the textbook 2-way paired swap.
        donor_a, patient_a = _make_donor(BloodType.B), _make_patient(BloodType.A)
        donor_b, patient_b = _make_donor(BloodType.A), _make_patient(BloodType.B)
        node_a = _make_node(donor_a, patient_a)
        node_b = _make_node(donor_b, patient_b)

        graph = build_exchange_graph(
            nodes=[node_a, node_b],
            donor_typing_entries_by_donor={
                donor_a.id: _donor_typing_rows(donor_a.id),
                donor_b.id: _donor_typing_rows(donor_b.id),
            },
            patient_typing_entries_by_patient={
                patient_a.id: _patient_typing_rows(patient_a.id),
                patient_b.id: _patient_typing_rows(patient_b.id),
            },
            patient_antibodies_by_patient={},
        )

        edge_pairs = {(edge.from_pair_id, edge.to_pair_id) for edge in graph.edges}
        assert edge_pairs == {
            (node_a.pair_id, node_b.pair_id),
            (node_b.pair_id, node_a.pair_id),
        }

    def test_no_edge_when_the_cross_pairing_is_still_abo_incompatible(self):
        # Both recipients are O (universal recipient constraint: only
        # accepts O) but both donors are A -- swapping doesn't help either.
        donor_a, patient_a = _make_donor(BloodType.A), _make_patient(BloodType.O)
        donor_b, patient_b = _make_donor(BloodType.A), _make_patient(BloodType.O)
        node_a = _make_node(donor_a, patient_a)
        node_b = _make_node(donor_b, patient_b)

        graph = build_exchange_graph(
            nodes=[node_a, node_b],
            donor_typing_entries_by_donor={
                donor_a.id: _donor_typing_rows(donor_a.id),
                donor_b.id: _donor_typing_rows(donor_b.id),
            },
            patient_typing_entries_by_patient={
                patient_a.id: _patient_typing_rows(patient_a.id),
                patient_b.id: _patient_typing_rows(patient_b.id),
            },
            patient_antibodies_by_patient={},
        )

        assert graph.edges == []

    def test_graph_edge_flags_antibody_against_a_locus_the_donor_lacks_typing_for(self):
        # N1 regression, at the build_exchange_graph level: donor_a is only
        # typed at A/B/DRB1 (MATCHING_TYPING), and patient_b holds an
        # anti-DQ7 antibody. The resulting donor_a -> patient_b edge must
        # carry requires_review, not silently read as a clean DSA screen.
        donor_a, patient_a = _make_donor(BloodType.B), _make_patient(BloodType.A)
        donor_b, patient_b = _make_donor(BloodType.A), _make_patient(BloodType.B)
        node_a = _make_node(donor_a, patient_a)
        node_b = _make_node(donor_b, patient_b)

        graph = build_exchange_graph(
            nodes=[node_a, node_b],
            donor_typing_entries_by_donor={
                donor_a.id: _donor_typing_rows(donor_a.id),
                donor_b.id: _donor_typing_rows(donor_b.id),
            },
            patient_typing_entries_by_patient={
                patient_a.id: _patient_typing_rows(patient_a.id),
                patient_b.id: _patient_typing_rows(patient_b.id),
            },
            patient_antibodies_by_patient={
                patient_b.id: [PatientAntibody(antigen="DQ7", mfi=9000.0)],
            },
        )

        edge = next(
            e for e in graph.edges
            if e.from_pair_id == node_a.pair_id and e.to_pair_id == node_b.pair_id
        )
        assert edge.result.is_compatible is True
        assert edge.result.dsa_result.requires_review is True
        assert [a.antigen for a in edge.result.dsa_result.untyped_locus_antibodies] == ["DQ7"]
