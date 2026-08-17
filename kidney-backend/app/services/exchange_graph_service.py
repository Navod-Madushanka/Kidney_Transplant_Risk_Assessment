# app/services/exchange_graph_service.py
"""
Builds the paired-exchange candidate graph: nodes are (donor, intended
recipient) pairs that are themselves ABO/HLA/DSA-incompatible -- exactly the
donors donor_search_service.py excludes from the ordinary cross-hospital
pool (see that module's docstring) because they're committed to one
specific relative. A paired exchange lets two or more such incompatible
pairs swap donors instead: pair i's donor gives to pair j's recipient, and
so on around a cycle. Directly-compatible pairs don't need a swap and are
excluded from the pool entirely -- both because they should just transplant
directly, and to keep this module's O(n^2) edge-scoring and
exchange_matching_service's O(n^3) cycle enumeration small.

Deliberately split into a pure, DB-free half (evaluate_pair_edge,
build_exchange_graph) and a DB-facing half (load_exchange_pool), the same
split donor_search_service/match_pipeline use elsewhere -- so
scripts/exchange_policy_comparison.py can build a graph from synthetic data
without touching the database.

This is a read-only, advisory computation: nothing here writes to the
database or transitions donor/patient status. Acting on a discovered cycle
is a separate, not-yet-built step.
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.doctor import Doctor
from app.models.donor import Donor
from app.models.donor_hla_typing import DonorHLATyping
from app.models.enums import DonorStatus
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.models.patient_hla_typing import PatientHLATyping
from app.services.abo_service import ABOResult, check_abo_compatibility
from app.services.antibody_profile_service import get_patient_antibody_profiles_bulk
from app.services.dsa_service import DSAResult, PatientAntibody, check_dsa
from app.services.hla_mismatch_service import (
    MISMATCH_COUNTED_LOCI,
    MismatchResult,
    calculate_mismatch_result,
)
from app.services.hla_typing_service import (
    build_partial_typing_dict,
    get_donor_hla_typing_entries_bulk,
    get_patient_hla_typing_entries_bulk,
    hla_antigen_designation,
    normalize_antibody_antigen,
)
from app.services.lkdpi_input_adapter import lkdpi_input_from_records
from app.services.lkdpi_service import LKDPIResult, calculate_lkdpi


@dataclass
class ExchangePairNode:
    """One incompatible (donor, intended recipient) pair -- a node in the
    exchange graph. `pair_id` is the donor's id: each donor has at most one
    intended recipient (Donor.intended_recipient_id), so it uniquely
    identifies the pair. A patient with more than one candidate donor
    appears as more than one node here -- see exchange_matching_service.py's
    module docstring for that known MVP limitation.
    """

    donor: Donor
    patient: Patient
    donor_hospital_name: str
    donor_doctor_full_name: str
    donor_doctor_email: str
    patient_hospital_name: str
    patient_doctor_full_name: str
    patient_doctor_email: str

    @property
    def pair_id(self) -> uuid.UUID:
        return self.donor.id


@dataclass
class PairEdgeResult:
    is_compatible: bool
    abo_result: ABOResult
    mismatch_result: MismatchResult
    dsa_result: DSAResult
    # LKDPI for this specific directed edge (donor -> recipient), if this
    # donor/recipient pair has the inputs for it -- see
    # app/services/lkdpi_service.py. None both when the edge is incompatible
    # (evaluate_pair_edge never computes it in that case -- see below) and
    # when either side is missing an LKDPI input. Only used by
    # exchange_matching_service.py's max_lkdpi_quality weight policy.
    lkdpi_result: LKDPIResult | None = None


@dataclass
class ExchangeEdge:
    from_pair_id: uuid.UUID  # donor's pair
    to_pair_id: uuid.UUID  # recipient's pair
    result: PairEdgeResult


@dataclass
class ExchangeGraph:
    nodes: list[ExchangePairNode]
    edges: list[ExchangeEdge]  # only compatible edges -- see build_exchange_graph
    # Aggregate rejection-reason counts for every ordered pair build_exchange_graph
    # scored but did NOT turn into an edge, keyed by the donor's pair_id
    # (outbound_blocked) or the recipient's pair_id (inbound_blocked). Exists
    # so exchange_explanation_service.py can answer "why wasn't this pair
    # matched" without persisting or returning the full O(n^2) result matrix
    # (see that module's docstring) -- only these per-pair aggregate counts
    # are ever exposed.
    outbound_blocked: dict[uuid.UUID, dict[str, int]] = field(default_factory=dict)
    inbound_blocked: dict[uuid.UUID, dict[str, int]] = field(default_factory=dict)


@dataclass
class ExchangePoolData:
    """Everything load_exchange_pool fetched, shaped so build_exchange_graph
    can consume it directly without re-querying anything."""

    nodes: list[ExchangePairNode]
    donor_typing_entries_by_donor: dict[uuid.UUID, list[DonorHLATyping]]
    patient_typing_entries_by_patient: dict[uuid.UUID, list[PatientHLATyping]]
    patient_antibodies_by_patient: dict[uuid.UUID, list[PatientAntibody]]


def evaluate_pair_edge(
    patient_typing: dict[str, list[str]],
    donor_typing: dict[str, list[str]],
    patient_antibodies: list[PatientAntibody],
    donor_hla_antigens: list[str],
    patient_blood_type: str,
    donor_blood_type: str,
) -> PairEdgeResult:
    """Scores one directed donor -> recipient edge: would this specific
    donor's kidney be offered to this specific recipient? Composes the same
    three gated checks match_pipeline.py runs (ABO, HLA mismatch, DSA)
    unchanged -- this is the reusable-service-layering payoff, not a
    reimplementation. Deliberately skips match_pipeline's sensitization/cPRA
    step (population-level, not pair-specific -- see pra_gate_removed note
    in match_pipeline.py) and crossmatch (needs a same-day lab result that
    doesn't exist for a hypothetical swap).
    """
    abo_result = check_abo_compatibility(patient_blood_type, donor_blood_type)
    mismatch_result = calculate_mismatch_result(patient_typing, donor_typing)
    dsa_result = check_dsa(patient_antibodies, donor_hla_antigens)

    is_compatible = (
        abo_result.is_compatible
        and not mismatch_result.is_halted
        and not dsa_result.is_halted
    )
    return PairEdgeResult(
        is_compatible=is_compatible,
        abo_result=abo_result,
        mismatch_result=mismatch_result,
        dsa_result=dsa_result,
    )


def _rejection_reason(result: PairEdgeResult) -> str:
    """Classifies why an incompatible directed edge was rejected, for the K7
    "why wasn't this pair matched" aggregate counts. A rejected edge can in
    principle fail more than one gate at once (evaluate_pair_edge computes
    all three unconditionally); this picks one reason per edge in a fixed
    priority -- ABO first since it's the most structural, then the DSA halt,
    then the mismatch halt -- so the aggregate counts stay a simple
    dict[str, int] rather than double-counting one rejected edge under two
    reasons."""
    if not result.abo_result.is_compatible:
        return "abo"
    if result.dsa_result.is_halted:
        return "dsa_strong"
    return "mismatch"


def _donor_hla_antigens(donor_typing_entries: list[DonorHLATyping]) -> list[str]:
    return [
        hla_antigen_designation(row.locus.value, allele)
        for row in donor_typing_entries
        for allele in (row.allele_1, row.allele_2)
    ]


def _edge_lkdpi(donor: Donor, patient: Patient, edge_result: PairEdgeResult) -> LKDPIResult:
    """Thin wrapper over the shared lkdpi_input_adapter (see E7.3) -- this
    used to hand-roll its own copy of the same ORM->LKDPIInput conversion
    match_pipeline.py builds, which had already drifted once."""
    return calculate_lkdpi(
        lkdpi_input_from_records(
            donor,
            patient,
            edge_result.mismatch_result,
            abo_incompatible=not edge_result.abo_result.is_compatible,
        )
    )


def build_exchange_graph(
    nodes: list[ExchangePairNode],
    donor_typing_entries_by_donor: dict[uuid.UUID, list[DonorHLATyping]],
    patient_typing_entries_by_patient: dict[uuid.UUID, list[PatientHLATyping]],
    patient_antibodies_by_patient: dict[uuid.UUID, list[PatientAntibody]],
) -> ExchangeGraph:
    """Pure, DB-free: scores every donor in `nodes` against every OTHER
    node's recipient (O(n^2) pairwise evaluations) and keeps only the
    compatible directed edges -- an incompatible ordered pair simply isn't
    an edge in the exchange graph, per the module docstring.
    """
    prepared: dict[uuid.UUID, dict] = {}
    for node in nodes:
        donor_entries = donor_typing_entries_by_donor.get(node.donor.id, [])
        prepared[node.pair_id] = {
            "donor_typing": build_partial_typing_dict(donor_entries, MISMATCH_COUNTED_LOCI),
            "donor_hla_antigens": _donor_hla_antigens(donor_entries),
            "patient_typing": build_partial_typing_dict(
                patient_typing_entries_by_patient.get(node.patient.id, []),
                MISMATCH_COUNTED_LOCI,
            ),
            "patient_antibodies": patient_antibodies_by_patient.get(node.patient.id, []),
        }

    edges: list[ExchangeEdge] = []
    outbound_blocked: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    inbound_blocked: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for donor_node in nodes:
        donor_data = prepared[donor_node.pair_id]
        for recipient_node in nodes:
            if recipient_node.pair_id == donor_node.pair_id:
                continue
            recipient_data = prepared[recipient_node.pair_id]
            result = evaluate_pair_edge(
                patient_typing=recipient_data["patient_typing"],
                donor_typing=donor_data["donor_typing"],
                patient_antibodies=recipient_data["patient_antibodies"],
                donor_hla_antigens=donor_data["donor_hla_antigens"],
                patient_blood_type=recipient_node.patient.blood_type.value,
                donor_blood_type=donor_node.donor.blood_type.value,
            )
            if result.is_compatible:
                # LKDPI is only needed on edges that actually make it into
                # the graph -- computing it for every scored-but-rejected
                # pair above would be wasted work (evaluate_pair_edge stays
                # ABO/mismatch/DSA only, same as before).
                result.lkdpi_result = _edge_lkdpi(donor_node.donor, recipient_node.patient, result)
                edges.append(
                    ExchangeEdge(
                        from_pair_id=donor_node.pair_id,
                        to_pair_id=recipient_node.pair_id,
                        result=result,
                    )
                )
            else:
                # Aggregate-only (K7): this ordered pair never becomes an
                # edge, and its full PairEdgeResult is discarded right here
                # -- only the reason tally per pair_id survives, so this
                # stays O(n^2) in time but O(n) in the memory it retains,
                # same as the compatible-edge path already was.
                reason = _rejection_reason(result)
                outbound_blocked[donor_node.pair_id][reason] += 1
                inbound_blocked[recipient_node.pair_id][reason] += 1

    return ExchangeGraph(
        nodes=nodes,
        edges=edges,
        outbound_blocked={pid: dict(counts) for pid, counts in outbound_blocked.items()},
        inbound_blocked={pid: dict(counts) for pid, counts in inbound_blocked.items()},
    )


async def load_exchange_pool(db: AsyncSession) -> ExchangePoolData:
    """Queries every donor tied to an intended recipient, joins each side's
    owning doctor/hospital for display (donor and recipient can belong to
    different doctors -- see donor.py's intended_recipient_id comment), and
    keeps only the pairs that are themselves incompatible: a directly-
    compatible pair should just transplant, not occupy a node in the
    exchange graph. Respects the same OCR-verification gate
    POST /compatibility/check enforces (app/api/compatibility.py) -- an
    unconfirmed HLA/antibody extraction shouldn't silently feed an
    optimizer either.
    """
    PatientDoctor = aliased(Doctor)
    PatientHospital = aliased(Hospital)

    result = await db.execute(
        select(Donor, Patient, Doctor, Hospital, PatientDoctor, PatientHospital)
        .join(Patient, Patient.id == Donor.intended_recipient_id)
        .join(Doctor, Doctor.id == Donor.doctor_id)
        .join(Hospital, Hospital.id == Doctor.hospital_id)
        .join(PatientDoctor, PatientDoctor.id == Patient.doctor_id)
        .join(PatientHospital, PatientHospital.id == PatientDoctor.hospital_id)
        .where(
            Donor.intended_recipient_id.is_not(None),
            Donor.status == DonorStatus.AVAILABLE,
            Donor.is_deleted.is_(False),
            Donor.hla_typing_verified.is_(True),
            Donor.details_verified.is_(True),
            Patient.is_deleted.is_(False),
            Patient.hla_typing_verified.is_(True),
            Patient.antibody_profile_verified.is_(True),
            Patient.details_verified.is_(True),
        )
    )
    rows = result.all()
    if not rows:
        return ExchangePoolData(
            nodes=[],
            donor_typing_entries_by_donor={},
            patient_typing_entries_by_patient={},
            patient_antibodies_by_patient={},
        )

    donor_ids = [donor.id for donor, *_ in rows]
    patient_ids = [patient.id for _, patient, *_ in rows]

    donor_typing_entries_by_donor = await get_donor_hla_typing_entries_bulk(db, donor_ids)
    patient_typing_entries_by_patient = await get_patient_hla_typing_entries_bulk(db, patient_ids)
    antibody_profiles_by_patient = await get_patient_antibody_profiles_bulk(db, patient_ids)
    patient_antibodies_by_patient: dict[uuid.UUID, list[PatientAntibody]] = {
        patient_id: [
            PatientAntibody(antigen=normalize_antibody_antigen(row.antigen), mfi=float(row.mfi))
            for row in profiles
        ]
        for patient_id, profiles in antibody_profiles_by_patient.items()
    }

    nodes: list[ExchangePairNode] = []
    for donor, patient, donor_doctor, donor_hospital, patient_doctor, patient_hospital in rows:
        donor_entries = donor_typing_entries_by_donor.get(donor.id, [])
        direct_result = evaluate_pair_edge(
            patient_typing=build_partial_typing_dict(
                patient_typing_entries_by_patient.get(patient.id, []), MISMATCH_COUNTED_LOCI
            ),
            donor_typing=build_partial_typing_dict(donor_entries, MISMATCH_COUNTED_LOCI),
            patient_antibodies=patient_antibodies_by_patient.get(patient.id, []),
            donor_hla_antigens=_donor_hla_antigens(donor_entries),
            patient_blood_type=patient.blood_type.value,
            donor_blood_type=donor.blood_type.value,
        )
        if direct_result.is_compatible or not direct_result.mismatch_result.data_completeness:
            # Compatible pairs would pass directly -- not an exchange
            # candidate. Incomplete typing is excluded for a different
            # reason (review #2 bug 11): calculate_mismatch_result worst-
            # cases a missing locus, which biases toward is_halted but
            # doesn't guarantee it (one missing locus can still coexist
            # with two genuinely-matching loci, landing under
            # MAX_ACCEPTABLE_MISMATCHES) -- so an untyped pair could
            # previously be *admitted* to the pool on guessed data with no
            # flag anywhere, same gap match_pipeline.py already closes at
            # Step 7 (see its data_completeness check) but this graph
            # builder hadn't.
            continue

        nodes.append(
            ExchangePairNode(
                donor=donor,
                patient=patient,
                donor_hospital_name=donor_hospital.name,
                donor_doctor_full_name=donor_doctor.full_name,
                donor_doctor_email=donor_doctor.email,
                patient_hospital_name=patient_hospital.name,
                patient_doctor_full_name=patient_doctor.full_name,
                patient_doctor_email=patient_doctor.email,
            )
        )

    return ExchangePoolData(
        nodes=nodes,
        donor_typing_entries_by_donor=donor_typing_entries_by_donor,
        patient_typing_entries_by_patient=patient_typing_entries_by_patient,
        patient_antibodies_by_patient=patient_antibodies_by_patient,
    )
