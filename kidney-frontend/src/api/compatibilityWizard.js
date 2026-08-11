// src/api/compatibilityWizard.js
import { apiPost } from "./client"
import {
  updatePatient,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  replacePatientSensitizationEvents,
} from "./patients"
import { updateDonor, replaceDonorHlaTypings } from "./donors"

// Runs the full wizard submission as a sequence of backend calls. Resumable:
// pass back the `progress` object from a previous failed attempt (thrown
// errors carry it as `error.progress`) and any step already marked done
// will be skipped rather than re-run.
//
// Part E: this no longer creates a patient/donor on submit. SubjectStep.jsx
// is where a doctor picks the two existing records this check runs
// against (wizardState.subject.patientId/donorId) — every write below
// updates those records instead, so a doctor can re-check the same real
// pair without hitting the NIC-uniqueness 409 a fresh create used to throw
// on a second check, and without silently forking a duplicate record for a
// person who already exists.
//
// onStepComplete(progress) fires after every successful step so the caller
// can persist progress into component state as it goes (not just at the
// end), so a page refresh mid-submission doesn't lose track of what's
// already been created.
export async function submitCompatibilityCheck(
  wizardState,
  progress = {},
  onStepComplete = () => {}
) {
  const next = { ...progress }

  async function completeStep(patch) {
    Object.assign(next, patch)
    onStepComplete({ ...next })
  }

  try {
    // undefined (no document at all finished OCR, so nothing to confirm)
    // vs an explicit true/false (person-details WAS populated by OCR --
    // could have come from any uploaded document, since PersonDetailsOcr
    // is merged across all of them, not owned by one fixed document type
    // the way HLA typing/bead-specificity are) -- see DetailsStep.jsx's
    // wasAnyDocumentOcrExtracted and the same undefined/true/false
    // contract on hlaOcrVerified below.
    const detailsOcrVerified = wasAnyDocumentOcrExtracted(wizardState)
      ? wizardState.ocr_verified.details
      : undefined

    // SubjectStep.jsx requires both to be set before Continue enables, so
    // these are always present by the time a submission starts -- not
    // re-derived or defaulted here.
    next.patientId ??= wizardState.subject.patientId
    next.donorId ??= wizardState.subject.donorId

    if (!next.patientDetailsDone) {
      await updatePatient(
        next.patientId,
        buildPatientUpdatePayload(
          wizardState.patient_details,
          wizardState.subject.patientRecord,
          detailsOcrVerified
        )
      )
      await completeStep({ patientDetailsDone: true })
    }

    if (!next.donorDetailsDone) {
      await updateDonor(
        next.donorId,
        buildDonorUpdatePayload(
          wizardState.donor_details,
          wizardState.subject.donorRecord,
          detailsOcrVerified
        )
      )
      await completeStep({ donorDetailsDone: true })
    }

    // undefined (not this document's OCR extraction status) vs an explicit
    // true/false (it WAS OCR-extracted, and here's whether the doctor
    // confirmed it) — see replacePatientHlaTypings's docstring. HlaTypingStep
    // /BeadSpecificityStep already block reaching this point at all unless
    // ocr_verified is true whenever wasOcrExtracted, so these are really
    // only ever `undefined` or `true` in practice; still computed from the
    // real extraction state rather than assumed, so a defensive caller
    // hitting this function directly can't accidentally mismark manual
    // entry as unverified OCR.
    const hlaOcrVerified = wasOcrExtracted(wizardState, "hla_typing_report")
      ? wizardState.ocr_verified.hla_typing
      : undefined
    const beadSpecificityOcrVerified =
      wasOcrExtracted(wizardState, "bead_specificity_page_1") ||
      wasOcrExtracted(wizardState, "bead_specificity_page_2")
        ? wizardState.ocr_verified.bead_specificity
        : undefined

    if (!next.patientHlaDone) {
      await replacePatientHlaTypings(next.patientId, wizardState.patient_hla, hlaOcrVerified)
      await completeStep({ patientHlaDone: true })
    }

    if (!next.donorHlaDone) {
      await replaceDonorHlaTypings(next.donorId, wizardState.donor_hla, hlaOcrVerified)
      await completeStep({ donorHlaDone: true })
    }

    if (!next.antibodyProfilesDone) {
      await replacePatientAntibodyProfiles(
        next.patientId,
        wizardState.bead_specificity,
        beadSpecificityOcrVerified
      )
      await completeStep({ antibodyProfilesDone: true })
    }

    const sensitizationEntries = buildSensitizationEntries(
      wizardState.sensitization,
      wizardState.sensitization_dates
    )
    if (!next.sensitizationDone) {
      // Replace, not append (see the matching backend endpoint's
      // docstring) -- the wizard's sensitization step is three booleans, a
      // complete statement of "as of right now," and this patient may
      // already have events on file from an earlier check against this
      // same linked record. Sent even when empty, to correctly clear any
      // previously-recorded events this run no longer confirms.
      await replacePatientSensitizationEvents(next.patientId, sensitizationEntries)
      await completeStep({ sensitizationDone: true })
    }

    if (!next.reportId) {
      const report = await apiPost("/compatibility/check", {
        patient_id: next.patientId,
        donor_id: next.donorId,
        ...(buildCrossmatchPayload(wizardState.crossmatch)
          ? { crossmatch: buildCrossmatchPayload(wizardState.crossmatch) }
          : {}),
      })
      await completeStep({ reportId: report.id, report })
      return report
    }

    return next.report
  } catch (err) {
    // Attach whatever progress *did* succeed before the failure, so the
    // caller can store it and resume on retry instead of starting over.
    err.progress = next
    throw err
  }
}

function wasOcrExtracted(wizardState, documentType) {
  return wizardState.extraction.documents[documentType]?.status === "done"
}

// Person-details (full_name/date_of_birth/blood_type/rh_factor) can be
// populated by OCR from ANY uploaded document -- PersonDetailsOcr is
// merged across all of them (see app/schemas/ocr.py), not owned by one
// fixed document type the way HLA typing/bead-specificity are. So "was
// this OCR-extracted at all" here means "did any document finish OCR",
// not one specific documentType.
function wasAnyDocumentOcrExtracted(wizardState) {
  return Object.values(wizardState.extraction.documents).some(
    (doc) => doc?.status === "done"
  )
}

// PatientUpdate/DonorUpdate are full-replace schemas (every clinical field
// has a default of None, not "leave unchanged") -- omitting a field here
// would silently wipe it, including exactly the LKDPI/donor-risk inputs
// this whole part exists to preserve across re-checks. `record` is the
// linked patient/donor snapshot SubjectStep.jsx fetched and stored on
// wizardState.subject.{patient,donor}Record; every field below except
// full_name/date_of_birth/nic_number (which `details` — DetailsStep's own
// state — owns) is carried through unchanged from it. blood_type/rh_factor
// are never sent: both are permanent once set and absent from
// PatientUpdate/DonorUpdate entirely (see E3.6's blood-type conflict guard
// on DetailsStep for what happens when OCR disagrees with them).
function buildPatientUpdatePayload(details, record, detailsVerified) {
  return {
    full_name: details.full_name.trim(),
    date_of_birth: details.date_of_birth,
    nic_number: details.nic_number.trim() || null,
    sex: record.sex,
    weight_kg: record.weight_kg,
    details_verified: detailsVerified,
  }
}

function buildDonorUpdatePayload(details, record, detailsVerified) {
  return {
    full_name: details.full_name.trim(),
    date_of_birth: details.date_of_birth,
    nic_number: details.nic_number.trim() || null,
    egfr: record.egfr,
    systolic_bp: record.systolic_bp,
    diastolic_bp: record.diastolic_bp,
    bmi: record.bmi,
    has_diabetes: record.has_diabetes,
    sex: record.sex,
    race: record.race,
    smoking_status: record.smoking_status,
    creatinine: record.creatinine,
    urine_acr: record.urine_acr,
    is_on_antihypertensive_medication: record.is_on_antihypertensive_medication,
    family_history_kidney_disease: record.family_history_kidney_disease,
    weight_kg: record.weight_kg,
    is_biologically_related: record.is_biologically_related,
    intended_recipient_id: record.intended_recipient_id,
    details_verified: detailsVerified,
  }
}

// Mirrors app/schemas/match_report.py's CrossmatchInput — only is_positive/
// t_cell_result/b_cell_result/remarks are sent; interpretation and
// test_date are reference-only fields the backend has no column for. Sent
// only once the doctor has actually confirmed a positive/negative reading
// (is_positive !== null) — the wizard's ReviewStep requires this before
// letting the check submit at all, but this function stays defensive so a
// resumed/retried submission never sends a half-confirmed crossmatch.
function buildCrossmatchPayload(crossmatch) {
  if (!crossmatch || crossmatch.is_positive === null || crossmatch.is_positive === undefined) {
    return null
  }
  return {
    is_positive: crossmatch.is_positive,
    t_cell_result: crossmatch.t_cell_result?.trim() || null,
    b_cell_result: crossmatch.b_cell_result?.trim() || null,
    remarks: crossmatch.remarks?.trim() || null,
  }
}

function buildSensitizationEntries(sensitization, sensitizationDates) {
  return Object.entries(sensitization)
    .filter(([, isOn]) => isOn)
    .map(([eventType]) => ({
      event_type: eventType,
      event_date: sensitizationDates[eventType],
    }))
}