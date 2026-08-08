// src/api/compatibilityWizard.js
import { apiPost } from "./client"
import {
  createPatient,
  replacePatientHlaTypings,
  replacePatientAntibodyProfiles,
  createSensitizationEvents,
} from "./patients"
import { createDonor, replaceDonorHlaTypings } from "./donors"

// Runs the full wizard submission as a sequence of backend calls. Resumable:
// pass back the `progress` object from a previous failed attempt (thrown
// errors carry it as `error.progress`) and any step already marked done
// will be skipped rather than re-run — critical since createPatient/
// createDonor aren't idempotent, and re-running them on retry would create
// duplicate records for the same person.
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
    if (!next.patientId) {
      const patient = await createPatient(buildPersonPayload(wizardState.patient_details))
      await completeStep({ patientId: patient.id })
    }

    if (!next.donorId) {
      const donor = await createDonor(buildPersonPayload(wizardState.donor_details))
      await completeStep({ donorId: donor.id })
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
      if (sensitizationEntries.length > 0) {
        await createSensitizationEvents(next.patientId, sensitizationEntries)
      }
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

function buildPersonPayload(details) {
  return {
    full_name: details.full_name.trim(),
    date_of_birth: details.date_of_birth,
    blood_type: details.blood_type,
    rh_factor: details.rh_factor,
    nic_number: details.nic_number.trim() || null,
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