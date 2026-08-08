// src/constants/donorStatus.js
//
// Mirrors kidney-backend/app/models/enums.py::DonorStatus. A donor's status
// is doctor-controlled (never set automatically from a compatibility check
// outcome) and determines whether they show up as a candidate in another
// doctor's cross-hospital search (see donorSearch.js) — only "available"
// donors are searchable.

export const DONOR_STATUS_OPTIONS = [
  { value: "available", label: "Available" },
  { value: "reserved", label: "Reserved" },
  { value: "under_workup", label: "Under workup" },
  { value: "transplanted", label: "Transplanted" },
  { value: "medically_unfit", label: "Medically unfit" },
  { value: "withdrawn", label: "Withdrawn" },
  { value: "deceased", label: "Deceased" },
]

const DONOR_STATUS_BADGE_STATUS = {
  available: "clear",
  reserved: "pending",
  under_workup: "pending",
  transplanted: "neutral",
  medically_unfit: "fail",
  withdrawn: "neutral",
  deceased: "neutral",
}

const DONOR_STATUS_LABEL = {
  available: "Available",
  reserved: "Reserved",
  under_workup: "Under workup",
  transplanted: "Transplanted",
  medically_unfit: "Medically unfit",
  withdrawn: "Withdrawn",
  deceased: "Deceased",
}

/**
 * Usage:
 *   const { status, label } = donorStatusBadgeProps(donor.status)
 *   <Badge status={status}>{label}</Badge>
 */
export function donorStatusBadgeProps(donorStatus) {
  return {
    status: DONOR_STATUS_BADGE_STATUS[donorStatus] ?? "neutral",
    label: DONOR_STATUS_LABEL[donorStatus] ?? donorStatus,
  }
}
