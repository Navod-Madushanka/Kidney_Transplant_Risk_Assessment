// src/utils/ocrNormalize.js
//
// Converts the raw OCR batch response (strings straight off the document)
// into the shapes the wizard reducer expects: ISO dates for <input
// type="date">, bare ABO codes for the blood-type selects, and numeric
// MFI values for the bead specificity table. Kept separate from the
// reducer so the reducer stays a pure "merge this shape into state"
// function, and all the real-world parsing quirks live in one place.

const MONTHS = {
  jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
  jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
}

export function parseOcrDate(raw) {
  if (!raw) return ""
  const trimmed = raw.trim()

  // DD-Mon-YYYY, e.g. "16-Jan-1980"
  const monthMatch = trimmed.match(/^(\d{1,2})[-\s](\w{3})\w*[-\s](\d{4})$/)
  if (monthMatch) {
    const [, day, monthName, year] = monthMatch
    const month = MONTHS[monthName.toLowerCase().slice(0, 3)]
    if (month) return `${year}-${month}-${day.padStart(2, "0")}`
  }

  // DD.MM.YYYY or DD/MM/YYYY, e.g. "21.03.1976"
  const numericMatch = trimmed.match(/^(\d{1,2})[.\/](\d{1,2})[.\/](\d{4})$/)
  if (numericMatch) {
    const [, day, month, year] = numericMatch
    return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`
  }

  return ""
}

export function parseOcrBloodType(raw) {
  if (!raw) return ""
  // "B Positive" / "B Pos" / "B+" -> "B". Only the ABO group is stored;
  // Rh factor isn't part of BLOOD_TYPE_OPTIONS today.
  const match = raw.trim().match(/^(AB|A|B|O)/i)
  return match ? match[1].toUpperCase() : ""
}

export function parseOcrMfi(raw) {
  if (!raw) return null
  const cleaned = raw.replace(/[^\d.]/g, "")
  const value = Number(cleaned)
  return Number.isFinite(value) && cleaned !== "" ? value : null
}

export function normalizeOcrBatchResponse(response) {
  const patientDetails = {
    full_name: response.patient_details?.full_name || "",
    nic_number: response.patient_details?.nic_number || "",
    date_of_birth: parseOcrDate(response.patient_details?.date_of_birth),
    blood_type: parseOcrBloodType(response.patient_details?.blood_type),
  }

  const donorDetails = {
    full_name: response.donor_details?.full_name || "",
    nic_number: response.donor_details?.nic_number || "",
    date_of_birth: parseOcrDate(response.donor_details?.date_of_birth),
    blood_type: parseOcrBloodType(response.donor_details?.blood_type),
  }

  const beadSpecificity = (response.bead_specificity || [])
    .map((entry) => ({ antigen: entry.antigen, mfi: parseOcrMfi(entry.mfi) }))
    .filter((entry) => entry.antigen && entry.mfi !== null)

  return {
    patientDetails,
    donorDetails,
    patientHla: response.patient_hla || [],
    donorHla: response.donor_hla || [],
    beadSpecificity,
    crossmatch: response.crossmatch || null,
  }
}