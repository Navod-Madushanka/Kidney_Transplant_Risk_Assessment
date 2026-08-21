# app/tests/integration/test_compatibility.py
"""
Integration coverage for the compatibility-check pipeline through the real
HTTP API. The pipeline's individual stages (ABO, mismatch bucketing, PRA
bucketing, DSA, crossmatch, risk classification, sensitization, legacy risk
tiering) already have thorough unit coverage in app/tests/unit/ — these
tests instead check that the API wires patient/donor records through the
whole Step 1-7 sequence correctly and persists/returns the right thing.

Step 4 (PRA) no longer has a reject path at all — it briefly did, but
rejecting a pairing on population-level cPRA (rather than a pair-specific
test like Steps 5/6) was a clinical category error, reverted 2026-08-08.
See match_pipeline.py's module docstring and
test_risk_classification.py::test_pra_above_60_percent_is_not_scored_and_returns_none
for the regression coverage of what used to be the reject path. cPRA is now
calculated against a frozen reference table
(app/reference_data/hla_antigen_frequencies.py) rather than this system's
own database, so it always has "sufficient data" regardless of how many
patients/donors exist in the test DB — the bucket math itself is covered
precisely and quickly in test_pra_bucket_service.py.

Step 3 (mismatches) used to be unreachable too: with exactly two alleles per
locus across the three counted loci (A/B/DRB1), the maximum possible
mismatch count is 6 — the same number MAX_ACCEPTABLE_MISMATCHES was
compared against with a strict `>`, so a full 6/6 mismatch could never
actually halt. Fixed by comparing with `>=` instead (see
hla_mismatch_service.py); test_full_mismatch_halts_step_3 below is the
regression test for the fix, alongside the unit-level
test_hla_mismatch_service.py::test_maximum_reachable_mismatches_halts_the_gate.
"""
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.match_report import MatchReport
from app.tests.conftest import (
    COMPATIBLE_DONOR_HLA,
    COMPATIBLE_PATIENT_HLA,
    create_donor,
    create_patient,
    register_test_doctor,
)

NEGATIVE_CROSSMATCH = {
    "is_positive": False,
    "t_cell_result": "Negative",
    "b_cell_result": "Negative",
}

POSITIVE_CROSSMATCH = {
    "is_positive": True,
    "t_cell_result": "Positive",
    "b_cell_result": "Negative",
}


async def test_check_compatibility_requires_existing_patient_and_donor(auth_client: AsyncClient):
    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": "00000000-0000-0000-0000-000000000000",
            "donor_id": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 404


async def test_abo_incompatible_pair_halts_before_hla_scoring(auth_client: AsyncClient):
    # Recipient O only accepts an O donor (app/reference_data/abo_compatibility.py)
    # — pairing with an A donor should halt immediately. Typing is fully
    # entered here (irrelevant to the point of this test) purely so the
    # endpoint's completeness precondition doesn't intercept the request
    # before Step 1 ever runs -- the assertions below are what actually
    # prove ABO halts before Step 3+ touch it.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_abo_fail"
    assert body["abo_result"]["is_compatible"] is False
    assert body["sensitization_result"] is None
    assert body["hla_scoring_result"] is None
    assert body["outcome"]["verdict"] == "not_compatible"
    assert body["outcome"]["risk_level"] is None
    assert body["outcome"]["determined_at_step"] == 1
    assert "O" in body["outcome"]["detail"]
    assert "A" in body["outcome"]["detail"]


async def test_full_mismatch_halts_step_3(auth_client: AsyncClient):
    # Regression test: a genuine 6/6 mismatch across A/B/DRB1 (every donor
    # allele absent from the patient at every counted locus) used to sail
    # through Step 3 uncontested, since is_halted compared with a strict `>`
    # against MAX_ACCEPTABLE_MISMATCHES (6) -- the same number as the
    # maximum reachable count, making the reject path dead code. See the
    # module docstring above and hla_mismatch_service.py.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "11", "allele_2": "12"},
            {"locus": "B", "allele_1": "17", "allele_2": "18"},
            {"locus": "DRB1", "allele_1": "13", "allele_2": "14"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_mismatch_reject"
    assert body["mismatch_result"]["total_mismatches"] == 6
    assert body["mismatch_result"]["is_halted"] is True
    assert body["pra_bucket_result"] is None
    assert body["final_risk_level"] is None
    assert body["outcome"]["verdict"] == "not_compatible"
    assert body["outcome"]["determined_at_step"] == 3


async def test_dsa_match_halts_before_hla_scoring(auth_client: AsyncClient):
    # ABO-compatible pair (O -> O), but the patient carries a high-MFI
    # antibody against an antigen the donor actually has — should halt on
    # the DSA check before HLA scoring ever runs (app/services/dsa_service.py).
    # Patient and donor A/B/DRB1 typing is given here purely so Step 3 (HLA
    # mismatches, gated separately — see test_full_mismatch_halts_step_3)
    # passes cleanly and this test actually reaches the DSA gate under test;
    # matching alleles on both sides keep the mismatch count at 0.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "40"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B7", "mfi": 6000}],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "40"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_dsa_trigger"
    assert body["dsa_result"]["is_halted"] is True
    assert body["hla_scoring_result"] is None
    assert body["outcome"]["verdict"] == "not_compatible"
    assert body["outcome"]["determined_at_step"] == 5


async def test_dsa_match_on_drb1_locus_halts(auth_client: AsyncClient):
    # Regression test for a real bug (fixed 2026-08-02): DSA antigen
    # designations for DRB1/DQB1/DPB1 used to be built as "DRB113" etc.
    # instead of the serological "DR13" a real antibody screen actually
    # uses, so a genuine donor-specific antibody at these loci was silently
    # invisible to this gate. See hla_antigen_designation() in
    # app/services/hla_typing_service.py.
    # Patient and donor A/B/DRB1 typing (matching, so the mismatch count
    # stays at 0) is given purely so Step 3 passes and this test reaches
    # the DSA gate under test — see test_full_mismatch_halts_step_3 for the
    # separate Step 3 gate coverage.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "13", "allele_2": "14"},
        ],
    )
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "DR13", "mfi": 6000}],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "13", "allele_2": "14"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_dsa_trigger"
    assert body["dsa_result"]["is_halted"] is True
    assert body["dsa_result"]["matches"][0]["antigen"] == "DR13"


async def test_dsa_match_on_c_locus_halts(auth_client: AsyncClient):
    # Regression test for a real bug (found 2026-08-03 running the full
    # pipeline against a real shared bead-specificity chart): unlike A/B,
    # HLA-C's serological antigen names are conventionally prefixed "Cw"
    # (Cw1..Cw18), not the bare locus letter -- hla_antigen_designation used
    # to build "C3" for a C*03 donor allele, which never matches a real
    # antibody screen's "Cw3". See hla_antigen_designation() in
    # app/services/hla_typing_service.py.
    # Patient and donor A/B/DRB1 typing (matching, so the mismatch count
    # stays at 0) is given purely so Step 3 passes and this test reaches
    # the DSA gate under test — C isn't a counted locus (see
    # MISMATCH_COUNTED_LOCI), but A/B/DRB1 still need real data on both
    # sides or Step 3 worst-cases them as missing. See
    # test_full_mismatch_halts_step_3 for the separate Step 3 gate coverage.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "Cw3", "mfi": 6000}],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "08"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
            {"locus": "C", "allele_1": "03", "allele_2": "07"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_dsa_trigger"
    assert body["dsa_result"]["is_halted"] is True
    assert body["dsa_result"]["matches"][0]["antigen"] == "Cw3"


async def test_dsa_match_on_b_locus_with_bw_suffix_halts(auth_client: AsyncClient):
    # Regression test for a real bug (found 2026-08-03 running the full
    # pipeline against a real shared bead-specificity chart): real charts
    # often record a B-locus antigen combined with its broad Bw4/Bw6
    # cross-reactive group in one string ("B7,Bw6"), while
    # hla_antigen_designation() only ever builds the bare antigen ("B7") --
    # every single B-locus row on that real chart carried this suffix, so
    # a genuine anti-B DSA was structurally unmatchable. See
    # normalize_antibody_antigen() in app/services/hla_typing_service.py.
    # Patient and donor A/B/DRB1 typing (matching, so the mismatch count
    # stays at 0) is given purely so Step 3 passes and this test reaches
    # the DSA gate under test — see test_full_mismatch_halts_step_3 for the
    # separate Step 3 gate coverage.
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "40"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B7,Bw6", "mfi": 6000}],
    )
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "07", "allele_2": "40"},
            {"locus": "DRB1", "allele_1": "03", "allele_2": "04"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_dsa_trigger"
    assert body["dsa_result"]["is_halted"] is True
    assert body["dsa_result"]["matches"][0]["antigen"] == "B7"


async def test_moderate_dsa_does_not_halt_but_flags_for_review(auth_client: AsyncClient):
    # Regression test for the 2026-08-08 severity-grading fix
    # (app/reference_data/dsa_threshold.py): a moderate-strength DSA (MFI
    # 2000-4999.999) used to halt the pipeline outright under the old flat
    # MFI-1000 cutoff. It should now proceed to crossmatch/completion with
    # dsa_result.requires_review set, not halt.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    # Donor typing carries B*40 on both alleles (see COMPATIBLE_DONOR_HLA in
    # conftest.py) -> donor_hla_antigens includes "B40".
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B40", "mfi": 3500}],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "completed"
    assert body["dsa_result"]["is_halted"] is False
    assert body["dsa_result"]["requires_review"] is True
    assert body["dsa_result"]["matches"][0]["antigen"] == "B40"
    assert body["dsa_result"]["matches"][0]["severity"] == "moderate"
    # Row 5: completed with a review flag present -> proceed_with_caution,
    # not compatible outright, even though every gate technically passed.
    assert body["outcome"]["verdict"] == "proceed_with_caution"
    assert any(flag["code"] == "dsa_requires_review" for flag in body["outcome"]["review_flags"])


async def test_full_pipeline_run_reaches_hla_scoring_and_risk_tier(auth_client: AsyncClient):
    # AB recipient accepts any donor blood type, and with no antibody
    # profile on file the DSA check can't trigger, so this pair should run
    # the full pipeline through to HLA scoring and cPRA — as long as a
    # crossmatch result is also submitted, since Step 6 now requires one to
    # reach "completed" rather than stopping at "pending_crossmatch".
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "completed"
    assert body["abo_result"]["is_compatible"] is True
    # Ground truth from the project's worked lab example
    # (app/tests/unit/test_hla_scoring_service.py): this exact typing pair
    # scores 6.5 on the legacy all-9-loci score, which lands in
    # "High-Moderate Risk" (5.25-7.0) — kept for reference alongside the
    # new Step 3/4/7 results below.
    assert body["hla_scoring_result"]["total_score"] == 6.5
    assert body["cpra_result"] is not None

    # New Step 3 (mismatches, A/B/DRB1 only): this typing pair has 3 total
    # mismatches across those three loci (2 at DRB1, 1 at B, 0 at A) -> the
    # "3-6 mismatches" bucket, which doesn't halt.
    assert body["mismatch_result"]["total_mismatches"] == 3
    assert body["mismatch_result"]["bucket_name"] == "3-6 mismatches"
    assert body["mismatch_result"]["is_halted"] is False

    # New Step 6 (crossmatch): negative, so it's recorded but doesn't halt.
    assert body["crossmatch_result"]["is_positive"] is False
    assert body["crossmatch_result"]["is_halted"] is False

    # New Step 4/7: this patient never submitted an antibody profile, so
    # sensitized_antigens is empty regardless of the reference table ->
    # cpra_percentage 0.0 -> the "<30%" PRA bucket (0 pts). Combined with
    # the "3-6 mismatches" mismatch bucket above (2 pts), Step 7 lands on
    # "High-Average Risk" (see risk_classification.py's scoring table).
    assert body["pra_bucket_result"]["has_sufficient_data"] is True
    assert body["pra_bucket_result"]["bucket_name"] == "<30%"
    assert body["pra_bucket_result"]["percent"] == 0.0
    assert body["final_risk_level"] == "High-Average Risk"

    # Row 6: completed, no review flags -> compatible, carrying the same
    # final_risk_level rather than a separate numeric score.
    assert body["outcome"]["verdict"] == "compatible"
    assert body["outcome"]["risk_level"] == "High-Average Risk"
    assert body["outcome"]["review_flags"] == []
    assert body["outcome"]["action_required"] is None


async def test_lkdpi_inputs_never_affect_verdict_or_risk_level(auth_client: AsyncClient):
    # Part E6: LKDPI (app/services/lkdpi_service.py) must never influence
    # the verdict, final_risk_level, or review flags -- it's a comparative
    # index (external C-statistic 0.55) sitting alongside the verdict, not
    # feeding into it. Two otherwise-identical pairs -- same blood types,
    # same HLA typing, same negative crossmatch -- one with every LKDPI
    # input populated and one with all of them left NULL, must produce
    # byte-identical overall_status/outcome/final_risk_level and differ
    # ONLY in lkdpi_result. Without this test, "keep them separate" is just
    # a docstring.
    patient_with = await create_patient(auth_client, blood_type="AB", sex="female", weight_kg=60)
    donor_with = await create_donor(
        auth_client,
        blood_type="O",
        sex="male",
        race="white",
        smoking_status="never",
        egfr=95,
        bmi=24.5,
        systolic_bp=118,
        weight_kg=78,
        is_biologically_related=True,
    )
    patient_without = await create_patient(auth_client, blood_type="AB")
    donor_without = await create_donor(auth_client, blood_type="O")

    for patient_id, donor_id in (
        (patient_with["id"], donor_with["id"]),
        (patient_without["id"], donor_without["id"]),
    ):
        await auth_client.put(f"/patients/{patient_id}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
        await auth_client.put(f"/donors/{donor_id}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response_with = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient_with["id"],
            "donor_id": donor_with["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )
    response_without = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient_without["id"],
            "donor_id": donor_without["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response_with.status_code == 201
    assert response_without.status_code == 201
    body_with = response_with.json()
    body_without = response_without.json()

    assert body_with["overall_status"] == body_without["overall_status"] == "completed"
    assert body_with["final_risk_level"] == body_without["final_risk_level"]
    assert body_with["outcome"]["verdict"] == body_without["outcome"]["verdict"]
    assert body_with["outcome"]["risk_level"] == body_without["outcome"]["risk_level"]
    assert body_with["outcome"]["review_flags"] == body_without["outcome"]["review_flags"]
    assert body_with["outcome"]["action_required"] == body_without["outcome"]["action_required"]

    # The only field allowed to differ between the two runs.
    assert body_with["lkdpi_result"]["has_sufficient_data"] is True
    assert body_without["lkdpi_result"]["has_sufficient_data"] is False
    assert body_with["lkdpi_result"] != body_without["lkdpi_result"]


async def test_incomplete_hla_typing_is_rejected_with_422_before_running_the_pipeline(
    auth_client: AsyncClient, db_session
):
    # The endpoint's own precondition (app/api/compatibility.py, backed by
    # compute_hla_mismatch_result in compatibility_precondition_service.py)
    # must catch incomplete A/B/DRB1 typing itself, not rely on
    # GET /compatibility/readiness -- a caller reaching this endpoint by any
    # route other than the wizard (Swagger, a script, a future client) never
    # sees that preview. Was previously reachable all the way to
    # run_match_pipeline with only one locus missing.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    # Donor typing omits DRB1 entirely -- Step 3 would otherwise worst-case
    # that locus instead of treating the missing side as a match.
    donor_typing_missing_drb1 = [
        row for row in COMPATIBLE_DONOR_HLA if row["locus"] != "DRB1"
    ]
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=donor_typing_missing_drb1)

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["missing_inputs"] == ["donor DRB1 typing"]
    assert "donor DRB1 typing" in body["detail"]["msg"]

    result = await db_session.execute(
        select(MatchReport).where(MatchReport.patient_id == uuid.UUID(patient["id"]))
    )
    assert result.scalar_one_or_none() is None


async def test_imputed_mismatches_reaching_the_halt_threshold_never_reach_the_pipeline(
    auth_client: AsyncClient,
):
    # Regression for the bug where 4 genuinely measured mismatches at A/B
    # plus a fully untyped DRB1 (imputed at its worst case, 2) summed to
    # exactly 6 -- MAX_ACCEPTABLE_MISMATCHES -- and halted Step 3 as if it
    # were a confirmed 6/6 reject. calculate_mismatch_result's is_halted no
    # longer fires on data that includes an imputed locus (see
    # test_hla_mismatch_service.py's unit-level regression coverage for
    # that), and this endpoint now blocks incomplete typing before the
    # pipeline runs at all -- so this case never even reaches Step 3 to ask
    # the question.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "01", "allele_2": "02"},
            {"locus": "B", "allele_1": "01", "allele_2": "02"},
            {"locus": "DRB1", "allele_1": "01", "allele_2": "02"},
        ],
    )
    # Donor A/B fully mismatch the patient (2 + 2 = 4 measured); DRB1 is
    # omitted entirely, which would worst-case it at 2 -- 4 + 2 = 6, the
    # same total as a real 6/6 -- if this ever reached Step 3.
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=[
            {"locus": "A", "allele_1": "11", "allele_2": "12"},
            {"locus": "B", "allele_1": "11", "allele_2": "12"},
        ],
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": NEGATIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["missing_inputs"] == ["donor DRB1 typing"]


async def test_positive_crossmatch_halts_after_dsa(auth_client: AsyncClient):
    # Same compatible pair as the full-pipeline test above (passes Steps
    # 1/3/4/5), but this time with a positive crossmatch — should halt at
    # the new Step 6 instead of reaching a final classification.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={
            "patient_id": patient["id"],
            "donor_id": donor["id"],
            "crossmatch": POSITIVE_CROSSMATCH,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "halted_crossmatch_positive"
    assert body["crossmatch_result"]["is_positive"] is True
    assert body["crossmatch_result"]["is_halted"] is True
    # Everything through Step 5 still ran and is on the report.
    assert body["dsa_result"] is not None
    assert body["mismatch_result"] is not None
    # But Step 7 never ran.
    assert body["final_risk_level"] is None
    assert body["hla_scoring_result"] is None
    assert body["outcome"]["verdict"] == "not_compatible"
    assert body["outcome"]["determined_at_step"] == 6


async def test_check_without_crossmatch_stops_at_pending(auth_client: AsyncClient):
    # Same compatible pair, but no crossmatch submitted at all — every gate
    # through Step 5 passes, but the check can't be treated as "completed"
    # without a crossmatch result.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["overall_status"] == "pending_crossmatch"
    assert body["crossmatch_result"] is None
    assert body["dsa_result"] is not None
    assert body["final_risk_level"] is None
    assert body["outcome"]["verdict"] == "cannot_assess"
    assert body["outcome"]["determined_at_step"] == 6


# ---------------------------------------------------------------------
# OCR verification gate (added 2026-08-08): a compatibility check must
# refuse to run at all against HLA typing / antibody-profile data that came
# from OCR extraction and hasn't been confirmed by a doctor yet, rather
# than trusting a vision-LLM misread into a hard reject. See
# Patient/Donor.hla_typing_verified / antibody_profile_verified and
# match_pipeline.py's module docstring.
# ---------------------------------------------------------------------


async def test_unverified_patient_details_blocks_the_check(auth_client: AsyncClient):
    # Review #2 bug 6: blood_type/DOB are OCR-extractable same as HLA
    # typing but previously had no verification gate at all.
    patient = await create_patient(auth_client, blood_type="AB", details_verified=False)
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "demographic details" in response.json()["detail"]


async def test_unverified_donor_details_blocks_the_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O", details_verified=False)

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "demographic details" in response.json()["detail"]


async def test_manual_patient_creation_without_details_verified_stays_trusted(
    auth_client: AsyncClient,
):
    # The overwhelming common case: a doctor creating a patient/donor by
    # hand never sends details_verified at all -- omitted means "not an
    # OCR write, no claim being made," same contract as ocr_verified.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201


async def test_unverified_patient_hla_typing_blocks_the_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=COMPATIBLE_PATIENT_HLA,
        params={"ocr_verified": "false"},
    )
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "patient's HLA typing" in response.json()["detail"]


async def test_unverified_donor_hla_typing_blocks_the_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(
        f"/donors/{donor['id']}/hla-typings",
        json=COMPATIBLE_DONOR_HLA,
        params={"ocr_verified": "false"},
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "donor's HLA typing" in response.json()["detail"]


async def test_unverified_antibody_profile_blocks_the_check(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    await auth_client.put(
        f"/patients/{patient['id']}/antibody-profiles",
        json=[{"antigen": "B7", "mfi": 500}],
        params={"ocr_verified": "false"},
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "antibody/bead-specificity profile" in response.json()["detail"]


async def test_blocked_check_never_creates_a_match_report(
    auth_client: AsyncClient, db_session
):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=COMPATIBLE_PATIENT_HLA,
        params={"ocr_verified": "false"},
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    assert response.status_code == 422

    result = await db_session.execute(
        select(MatchReport).where(MatchReport.patient_id == uuid.UUID(patient["id"]))
    )
    assert result.scalar_one_or_none() is None


async def test_confirming_ocr_verified_true_lets_the_check_proceed(auth_client: AsyncClient):
    # A doctor re-saving the same data with ocr_verified=true (having
    # reviewed it against the source document) clears the block.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=COMPATIBLE_PATIENT_HLA,
        params={"ocr_verified": "false"},
    )
    blocked = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    assert blocked.status_code == 422

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=COMPATIBLE_PATIENT_HLA,
        params={"ocr_verified": "true"},
    )
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    assert response.status_code == 201


async def test_replacing_hla_typing_without_ocr_verified_preserves_prior_unverified_state(
    auth_client: AsyncClient,
):
    # Review #2 bug 5: omitting ocr_verified used to unconditionally reset
    # hla_typing_verified back to True (trusted) even when the record's
    # current value was False -- a PUT with the query param simply left
    # off silently cleared the block, with no trace it happened.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(
        f"/patients/{patient['id']}/hla-typings",
        json=COMPATIBLE_PATIENT_HLA,
        params={"ocr_verified": "false"},
    )
    # Re-PUT the same data with ocr_verified omitted entirely -- must NOT
    # silently re-trust it.
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 422
    assert "patient's HLA typing" in response.json()["detail"]


async def test_manual_edits_without_ocr_verified_param_stay_trusted(auth_client: AsyncClient):
    # The overwhelming common case: a doctor typing HLA typing in by hand
    # (or editing it later via the patient/donor detail page) never sends
    # ocr_verified at all -- omitted means "not an OCR write, no claim being
    # made," same as before this feature existed.
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(auth_client, blood_type="O")

    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201


async def test_get_report_by_id(auth_client: AsyncClient):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    check = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    report_id = check.json()["id"]

    response = await auth_client.get(f"/compatibility/reports/{report_id}")

    assert response.status_code == 200
    assert response.json()["id"] == report_id


async def test_get_nonexistent_report_is_404(auth_client: AsyncClient):
    response = await auth_client.get(
        "/compatibility/reports/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


async def test_cannot_get_another_doctors_report(
    auth_client: AsyncClient, client: AsyncClient, db_session: AsyncSession
):
    patient = await create_patient(auth_client, blood_type="O")
    donor = await create_donor(auth_client, blood_type="A")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    check = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    report_id = check.json()["id"]

    other_doctor = await register_test_doctor(
        db_session,
        hospital_name="Other Hospital",
        email="third-doctor@example.com",
        password="another-secret-1234",
        full_name="Dr. Third",
    )
    login = await client.post(
        "/auth/login",
        json={"email": other_doctor["email"], "password": other_doctor["password"]},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/compatibility/reports/{report_id}", headers=other_headers)

    assert response.status_code == 404


async def test_full_check_allowed_against_non_owned_available_donor(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await second_auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 201
    assert response.json()["donor_id"] == donor["id"]


async def test_full_check_still_blocked_for_non_owned_non_available_donor(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O")
    await second_auth_client.put(f"/donors/{donor['id']}/status", json={"status": "reserved"})

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 404


async def test_full_check_blocked_for_available_donor_with_intended_recipient(
    auth_client: AsyncClient, second_auth_client: AsyncClient
):
    # A donor committed to another doctor's patient is "available" but not
    # actually free for the pool -- get_donor_for_compatibility_check must
    # reject it the same way search does (see donor_search_service.py).
    patient = await create_patient(auth_client, blood_type="AB")
    other_doctors_patient = await create_patient(second_auth_client, blood_type="AB")
    donor = await create_donor(
        second_auth_client, blood_type="O", intended_recipient_id=other_doctors_patient["id"]
    )

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )

    assert response.status_code == 404


async def test_cross_hospital_check_uses_distinct_audit_action(
    auth_client: AsyncClient, second_auth_client: AsyncClient, db_session
):
    patient = await create_patient(auth_client, blood_type="AB")
    donor = await create_donor(second_auth_client, blood_type="O")
    await auth_client.put(f"/patients/{patient['id']}/hla-typings", json=COMPATIBLE_PATIENT_HLA)
    await second_auth_client.put(f"/donors/{donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)

    response = await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": donor["id"]},
    )
    assert response.status_code == 201

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ran_cross_hospital_compatibility_check")
    )
    entries = result.scalars().all()

    assert len(entries) == 1
    assert entries[0].details["cross_hospital"] is True
    assert entries[0].details["donor_doctor_id"] == str(uuid.UUID(donor["doctor_id"]))

    # The same-doctor path must still use the original action name, unchanged.
    own_donor = await create_donor(auth_client, blood_type="O")
    await auth_client.put(f"/donors/{own_donor['id']}/hla-typings", json=COMPATIBLE_DONOR_HLA)
    await auth_client.post(
        "/compatibility/check",
        json={"patient_id": patient["id"], "donor_id": own_donor["id"]},
    )
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "ran_compatibility_check")
    )
    assert len(result.scalars().all()) == 1
