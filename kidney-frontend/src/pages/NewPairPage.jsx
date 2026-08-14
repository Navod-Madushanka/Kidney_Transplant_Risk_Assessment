// src/pages/NewPairPage.jsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { startExtractionJob } from "../api/ocr"
import { submitPairRegistration } from "../api/pairRegistration"
import { useExtractionJobPolling } from "../hooks/useExtractionJobPolling"
import { useBackgroundJobs } from "../hooks/useBackgroundJobs"
import { mergeDetails, hasAnyValue } from "../utils/ocrHydrate"
import { parseOcrDate } from "../utils/ocrNormalize"
import FileUpload from "../components/ui/FileUpload"
import Button from "../components/ui/Button"
import Card from "../components/ui/Card"
import ToggleSwitch from "../components/ui/ToggleSwitch"
import ExtractionProgressList from "../components/domain/ocr/ExtractionProgressList"
import PatientForm from "../components/domain/patient/PatientForm"
import DonorForm from "../components/domain/donor/DonorForm"
import HlaTypingEditor from "../components/domain/hla/HlaTypingEditor"

// Only the two joint documents are extracted -- see
// implementation-prompt-part-f.md F5.1/F6. The bead specificity pages are
// storage-only here: several minutes per page to read and not needed to
// create a record, so they're archived to the patient for the
// compatibility check to read later instead.
const DOCUMENT_SLOTS = [
  {
    slot: "hlaTypingReport",
    documentType: "hla_typing_report",
    label: "Histocompatibility Type-match Report",
    helperText: "Joint patient + donor HLA typing report",
    extractable: true,
  },
  {
    slot: "crossmatchReport",
    documentType: "crossmatch_report",
    label: "Histocompatibility / Crossmatch Report",
    helperText: "Joint patient + donor T-cell / B-cell crossmatch result",
    extractable: true,
  },
  {
    slot: "beadSpecificityPage1",
    label: "Bead Specificity Chart — Page 1",
    helperText: "Stored for the compatibility check — not read now",
    extractable: false,
  },
  {
    slot: "beadSpecificityPage2",
    label: "Bead Specificity Chart — Page 2",
    helperText: "Stored for the compatibility check — not read now",
    extractable: false,
  },
]

const EXTRACTABLE_SLOTS = DOCUMENT_SLOTS.filter((s) => s.extractable)

// Fed to BackgroundJobToast's ExtractionProgressList (see
// BackgroundJobsProvider.jsx) -- documentType is all it needs, since
// ExtractionProgressList already has friendly labels for both bead pages.
const BEAD_SPECIFICITY_JOB_SLOTS = [
  { documentType: "bead_specificity_page_1" },
  { documentType: "bead_specificity_page_2" },
]

function buildCrossmatchInput(crossmatch) {
  if (!crossmatch) return null
  const { t_cell_result, b_cell_result, interpretation, remarks, test_date } = crossmatch
  // The crossmatch report's date isn't run through parseOcrDate anywhere
  // upstream (normalizeOcrBatchResponse passes it through raw, since the
  // wizard's own CrossmatchInput has no date field to validate against) --
  // PairCrossmatchInput.test_date is a real `date` column, so an
  // unparseable raw string here would 422 the whole registration. Parse it
  // defensively and just drop it rather than risk that.
  const parsedDate = parseOcrDate(test_date) || null
  if (!t_cell_result && !b_cell_result && !interpretation && !remarks && !parsedDate) return null
  return {
    t_cell_result: t_cell_result || null,
    b_cell_result: b_cell_result || null,
    interpretation: interpretation || null,
    remarks: remarks || null,
    test_date: parsedDate,
  }
}

/**
 * Registers a patient and donor together in one screen, fed by the two lab
 * documents that actually cover both of them (see
 * implementation-prompt-part-f.md). Reuses PatientForm/DonorForm/
 * HlaTypingEditor as-is -- each keeps its own "Save" button and local
 * validation; this page stages what they hand back and fires the real
 * POST /pairs (plus file uploads) from the one "Register" action at the
 * bottom, once both sides are staged and any OCR-populated group has been
 * confirmed.
 */
export default function NewPairPage() {
  const navigate = useNavigate()
  const backgroundJobs = useBackgroundJobs()

  const [files, setFiles] = useState({
    hlaTypingReport: null,
    crossmatchReport: null,
    beadSpecificityPage1: null,
    beadSpecificityPage2: null,
  })
  const [extractError, setExtractError] = useState("")
  const [extraction, setExtraction] = useState({ jobId: null, status: "idle", documents: {} })
  const [extractionRan, setExtractionRan] = useState(false)

  const [ocrPatientDetails, setOcrPatientDetails] = useState({})
  const [ocrDonorDetails, setOcrDonorDetails] = useState({})
  const [ocrPatientHla, setOcrPatientHla] = useState([])
  const [ocrDonorHla, setOcrDonorHla] = useState([])
  const [ocrCrossmatch, setOcrCrossmatch] = useState(null)
  // Bumped whenever new OCR data lands for that side, and used as a `key`
  // on that side's form/editor -- PatientForm/DonorForm/HlaTypingEditor
  // all seed their state from `initialValues`/`initialEntries` once via
  // useState, so they don't pick up later prop changes on their own; this
  // forces a remount with the freshly-hydrated values instead.
  const [patientSectionKey, setPatientSectionKey] = useState(0)
  const [donorSectionKey, setDonorSectionKey] = useState(0)

  const [ocrConfirmed, setOcrConfirmed] = useState({ details: false, hlaTyping: false })

  const [patientPayload, setPatientPayload] = useState(null)
  const [donorPayload, setDonorPayload] = useState(null)
  const [patientHlaEntries, setPatientHlaEntries] = useState([])
  const [donorHlaEntries, setDonorHlaEntries] = useState([])

  const [progress, setProgress] = useState({})
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState("")

  useExtractionJobPolling({
    jobId: extraction.jobId,
    status: extraction.status,
    onDocumentDone: (_documentType, payload) => {
      const detailsChanged = hasAnyValue(payload.patientDetails) || hasAnyValue(payload.donorDetails)
      const hlaChanged = payload.patientHla?.length > 0 || payload.donorHla?.length > 0

      if (hasAnyValue(payload.patientDetails)) {
        setOcrPatientDetails((prev) => mergeDetails(prev, payload.patientDetails))
        setPatientSectionKey((k) => k + 1)
      }
      if (hasAnyValue(payload.donorDetails)) {
        setOcrDonorDetails((prev) => mergeDetails(prev, payload.donorDetails))
        setDonorSectionKey((k) => k + 1)
      }
      if (payload.patientHla?.length > 0) {
        setOcrPatientHla(payload.patientHla)
        setPatientSectionKey((k) => k + 1)
      }
      if (payload.donorHla?.length > 0) {
        setOcrDonorHla(payload.donorHla)
        setDonorSectionKey((k) => k + 1)
      }
      if (payload.crossmatch) {
        setOcrCrossmatch((prev) => ({ ...prev, ...payload.crossmatch }))
      }
      if (detailsChanged) setOcrConfirmed((prev) => ({ ...prev, details: false }))
      if (hlaChanged) setOcrConfirmed((prev) => ({ ...prev, hlaTyping: false }))
    },
    onStatusChange: (status, documents) => {
      setExtraction((prev) => ({ ...prev, status, documents }))
    },
  })

  const isExtracting = extraction.status === "running"
  const isExtractionDone = extraction.status === "done"
  const canExtract = Boolean(files.hlaTypingReport || files.crossmatchReport)
  const demographicsExtracted = hasAnyValue(ocrPatientDetails) || hasAnyValue(ocrDonorDetails)
  const hlaExtracted = ocrPatientHla.length > 0 || ocrDonorHla.length > 0

  async function handleExtract() {
    setExtractError("")
    try {
      const { job_id } = await startExtractionJob({
        hlaTypingReport: files.hlaTypingReport,
        crossmatchReport: files.crossmatchReport,
      })
      setExtractionRan(true)
      setExtraction({ jobId: job_id, status: "running", documents: {} })
    } catch (err) {
      setExtractError(err.message || "Couldn't start extraction. Please try again.")
    }
  }

  const patientInitialValues = {
    fullName: ocrPatientDetails.full_name || "",
    dateOfBirth: ocrPatientDetails.date_of_birth || "",
    bloodType: ocrPatientDetails.blood_type || "",
    rhFactor: ocrPatientDetails.rh_factor || "",
    nicNumber: ocrPatientDetails.nic_number || "",
  }
  const donorInitialValues = {
    fullName: ocrDonorDetails.full_name || "",
    dateOfBirth: ocrDonorDetails.date_of_birth || "",
    bloodType: ocrDonorDetails.blood_type || "",
    rhFactor: ocrDonorDetails.rh_factor || "",
    nicNumber: ocrDonorDetails.nic_number || "",
  }

  const canSubmit =
    Boolean(patientPayload) &&
    Boolean(donorPayload) &&
    (!demographicsExtracted || ocrConfirmed.details) &&
    (!hlaExtracted || ocrConfirmed.hlaTyping)

  async function handleRegister() {
    setSubmitError("")
    setIsSubmitting(true)
    try {
      const result = await submitPairRegistration(
        {
          patient: patientPayload,
          donor: donorPayload,
          patientHla: patientHlaEntries,
          donorHla: donorHlaEntries,
          crossmatch: buildCrossmatchInput(ocrCrossmatch),
          ocrVerified: extractionRan
            ? {
                details: demographicsExtracted ? ocrConfirmed.details : null,
                hla_typing: hlaExtracted ? ocrConfirmed.hlaTyping : null,
              }
            : null,
          files,
        },
        progress,
        setProgress
      )

      // Best-effort, fire-and-forget: the two bead-specificity pages are
      // stored-but-unread at registration time (see DOCUMENT_SLOTS' own
      // comment above) -- reading them now, in the background, means the
      // doctor doesn't have to re-transcribe the whole chart by hand later
      // in the compatibility wizard. A failure here shouldn't block
      // navigating to the newly-registered patient, since registration
      // itself already succeeded.
      if (files.beadSpecificityPage1 || files.beadSpecificityPage2) {
        try {
          const { job_id } = await startExtractionJob(
            {
              beadSpecificityPage1: files.beadSpecificityPage1,
              beadSpecificityPage2: files.beadSpecificityPage2,
            },
            result.patientId
          )
          backgroundJobs.startJob({
            jobId: job_id,
            label: `Bead specificity chart — ${patientPayload.full_name}`,
            documentSlots: BEAD_SPECIFICITY_JOB_SLOTS,
          })
        } catch {
          // Swallowed on purpose -- see comment above.
        }
      }

      navigate(`/patients/${result.patientId}`)
    } catch (err) {
      setProgress(err.progress || progress)
      setSubmitError(err.message || "Couldn't register this pair. Please try again.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div>
        <h1 className="text-[22px] font-bold text-text">Register patient &amp; donor</h1>
        <p className="text-[14px] text-text-muted mt-1">
          Register a patient and their donor together, in one screen — the two lab documents that
          cover both of them get filed against the pair instead of guessed onto one side.
        </p>
      </div>

      <Card>
        <Card.Header
          title="Documents"
          subtitle="Add whatever you have on hand, then tap Extract to auto-fill the forms below."
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {DOCUMENT_SLOTS.map(({ slot, label, helperText }) => (
            <FileUpload
              key={slot}
              label={label}
              helperText={helperText}
              accept="image/*,application/pdf"
              onFileSelect={(file) => setFiles((prev) => ({ ...prev, [slot]: file }))}
            />
          ))}
        </div>

        <div className="flex items-center gap-3 mt-5">
          <Button
            type="button"
            variant="secondary"
            loading={isExtracting}
            disabled={!canExtract || isExtracting}
            onClick={handleExtract}
          >
            {isExtracting ? "Reading documents…" : "Extract details"}
          </Button>
          {isExtractionDone && !extractError && (
            <span className="text-[13px] text-clear font-medium">
              Extracted — review the details below
            </span>
          )}
        </div>

        {Object.keys(extraction.documents).length > 0 && !isExtractionDone && (
          <ExtractionProgressList
            documentSlots={EXTRACTABLE_SLOTS}
            extractionDocuments={extraction.documents}
          />
        )}

        {extractError && <p className="text-[13px] text-high-risk font-medium mt-3">{extractError}</p>}
      </Card>

      <div>
        <h2 className="text-[17px] font-semibold text-text mb-1">Patient</h2>
        <p className="text-[13px] text-text-muted mb-3">
          Leaving sex/weight blank means LKDPI will be withheld for this pair rather than estimated.
        </p>
        <div className="flex flex-col gap-4">
          <PatientForm
            key={`patient-${patientSectionKey}`}
            initialValues={patientInitialValues}
            submitLabel={patientPayload ? "Patient details saved — update" : "Save patient details"}
            onSubmit={(payload) => {
              setPatientPayload(payload)
              return Promise.resolve()
            }}
          />
          <HlaTypingEditor
            key={`patient-hla-${patientSectionKey}`}
            loadState="loaded"
            initialEntries={ocrPatientHla}
            onSave={(entries) => {
              setPatientHlaEntries(entries)
              return Promise.resolve()
            }}
          />
        </div>
      </div>

      <div>
        <h2 className="text-[17px] font-semibold text-text mb-1">Donor</h2>
        <p className="text-[13px] text-text-muted mb-3">
          Leaving the clinical panel blank means LKDPI and the donor safety assessment will be
          withheld for this donor rather than estimated.
        </p>
        <div className="flex flex-col gap-4">
          <DonorForm
            key={`donor-${donorSectionKey}`}
            hideIntendedRecipientPicker
            initialValues={donorInitialValues}
            submitLabel={donorPayload ? "Donor details saved — update" : "Save donor details"}
            onSubmit={(payload) => {
              setDonorPayload(payload)
              return Promise.resolve()
            }}
          />
          <HlaTypingEditor
            key={`donor-hla-${donorSectionKey}`}
            loadState="loaded"
            initialEntries={ocrDonorHla}
            onSave={(entries) => {
              setDonorHlaEntries(entries)
              return Promise.resolve()
            }}
          />
        </div>
      </div>

      {(demographicsExtracted || hlaExtracted) && (
        <Card>
          <Card.Header title="Confirm OCR-extracted data" />
          <div className="flex flex-col gap-3">
            {demographicsExtracted && (
              <ToggleSwitch
                label="I have reviewed the patient/donor details against the source document"
                checked={ocrConfirmed.details}
                onChange={(checked) => setOcrConfirmed((prev) => ({ ...prev, details: checked }))}
              />
            )}
            {hlaExtracted && (
              <ToggleSwitch
                label="I have reviewed the HLA typing against the source document"
                checked={ocrConfirmed.hlaTyping}
                onChange={(checked) => setOcrConfirmed((prev) => ({ ...prev, hlaTyping: checked }))}
              />
            )}
          </div>
          {!canSubmit && (patientPayload || donorPayload) && (
            <p className="text-[13px] text-high-risk font-medium mt-2">
              Confirm the extracted data above before registering — this data was read by AI and
              hasn't been checked against the source document yet.
            </p>
          )}
        </Card>
      )}

      {submitError && <p className="text-[13px] text-high-risk font-medium">{submitError}</p>}

      <div className="flex justify-end">
        <Button size="lg" loading={isSubmitting} disabled={!canSubmit} onClick={handleRegister}>
          Register patient &amp; donor
        </Button>
      </div>
    </div>
  )
}
