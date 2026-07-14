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

    if (!next.patientHlaDone) {
      await replacePatientHlaTypings(next.patientId, wizardState.patient_hla)
      await completeStep({ patientHlaDone: true })
    }

    if (!next.donorHlaDone) {
      await replaceDonorHlaTypings(next.donorId, wizardState.donor_hla)
      await completeStep({ donorHlaDone: true })
    }

    if (!next.antibodyProfilesDone) {
      await replacePatientAntibodyProfiles(next.patientId, wizardState.bead_specificity)
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

function buildPersonPayload(details) {
  return {
    full_name: details.full_name.trim(),
    date_of_birth: details.date_of_birth,
    blood_type: details.blood_type,
    nic_number: details.nic_number.trim() || null,
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