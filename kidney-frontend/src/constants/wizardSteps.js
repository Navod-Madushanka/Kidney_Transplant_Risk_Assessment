// src/constants/wizardSteps.js
//
// Single source of truth for the wizard's step order, routes, and labels.
// Both StepProgress (visual indicator) and each step page (to know where
// "Continue" goes next) read from this, so the sequence is only ever
// defined once. Routes are relative segments under /checks/new/*.

export const WIZARD_STEPS = [
  { key: "subject", label: "Patient & Donor", path: "subject" },
  { key: "photos", label: "Photos", path: "photos" },
  { key: "details", label: "Confirm details", path: "details" },
  { key: "hla", label: "HLA Typing", path: "hla" },
  { key: "sensitization", label: "Sensitization", path: "sensitization" },
  { key: "bead-chart", label: "Bead Specificity", path: "bead-chart" },
  { key: "review", label: "Review & Submit", path: "review" },
]

export function wizardStepIndexForPath(path) {
  const index = WIZARD_STEPS.findIndex((step) => step.path === path)
  return index === -1 ? 0 : index
}