// src/pages/ReportDetailPage.jsx
import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { getReport } from "../api/reports"
import { reportBadgeProps } from "../constants/reportStatus"
import { useReviewedReports } from "../hooks/useReviewedReports"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Table from "../components/ui/Table"
import Button from "../components/ui/Button"

// Verdict hero + action-strip colors. Kept as its own map (not reusing
// Badge's STATUS_STYLES) because the hero needs the border token too, and
// "cannot_assess" here MUST resolve to the accent tokens, never the
// high-risk ones — it means "the system doesn't know yet," not "rejected."
// See app/reference_data/report_outcome.py (backend) for the verdict
// definitions this mirrors.
const VERDICT_HERO_STYLES = {
  not_compatible: {
    text: "text-high-risk",
    bg: "bg-high-risk-subtle",
    border: "border-high-risk/30",
  },
  proceed_with_caution: {
    text: "text-moderate",
    bg: "bg-moderate-subtle",
    border: "border-moderate/30",
  },
  compatible: {
    text: "text-clear",
    bg: "bg-clear-subtle",
    border: "border-clear/30",
  },
  cannot_assess: {
    text: "text-accent",
    bg: "bg-accent-subtle",
    border: "border-accent/25",
  },
}

const STEP_MARKER_STYLES = {
  pass: "bg-clear-subtle text-clear",
  halt: "bg-high-risk-subtle text-high-risk",
  flagged: "bg-moderate-subtle text-moderate",
  "not-reached": "bg-bg text-border border border-dashed border-border",
}

const STEP_MARKER_GLYPHS = {
  pass: "✓",
  halt: "✕",
  flagged: "!",
  "not-reached": "–",
}

function VerdictHero({ outcome }) {
  const style = VERDICT_HERO_STYLES[outcome.verdict] ?? VERDICT_HERO_STYLES.cannot_assess

  return (
    <div className={`rounded-lg border p-5 sm:p-6 ${style.bg} ${style.border}`}>
      <p className={`text-[28px] font-extrabold tracking-tight leading-tight ${style.text}`}>
        {outcome.verdict_label}
      </p>
      <p className="text-[15px] text-text mt-2 break-words">{outcome.detail}</p>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between mt-4 pt-4 border-t border-border/60">
        {outcome.risk_level ? (
          <Badge status={reportBadgeProps({ outcome }).status}>{outcome.risk_level}</Badge>
        ) : (
          <span />
        )}
        <span className="text-[13px] text-text-muted tabular-nums">
          Determined at step {outcome.determined_at_step} of {outcome.total_steps}
        </span>
      </div>
    </div>
  )
}

function ActionStrip({ actionRequired }) {
  if (!actionRequired) return null

  return (
    <div className="border-l-[3px] border-l-accent bg-surface border border-border rounded-md pl-4 pr-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-accent">Action required</p>
      <p className="text-[14px] text-text mt-1 break-words">{actionRequired}</p>
    </div>
  )
}

function ReviewFlags({ flags }) {
  if (!flags || flags.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[13px] font-semibold text-text-muted">Review flags</p>
      {flags.map((flag) => (
        <Card key={flag.code} padded={false} className="p-4 flex items-start gap-3">
          <span
            className="h-5 w-5 shrink-0 rounded bg-moderate-subtle text-moderate flex items-center justify-center text-[12px] font-bold mt-0.5"
            aria-hidden="true"
          >
            !
          </span>
          <div className="min-w-0">
            <p className="text-[14px] font-semibold text-text break-words">{flag.label}</p>
            <p className="text-[13px] text-text-muted mt-0.5 break-words">{flag.detail}</p>
          </div>
        </Card>
      ))}
    </div>
  )
}

// LKDPI band -> Badge's existing clear/moderate/high-moderate status keys
// (see Badge.jsx's STATUS_STYLES) so this card reuses the same color
// vocabulary as every other risk indicator in the app rather than a
// one-off palette.
const LKDPI_BAND_BADGE_STATUS = {
  excellent: "clear",
  good: "clear",
  moderate: "moderate",
  marginal: "high-moderate",
}

const LKDPI_BAND_TEXT_CLASS = {
  excellent: "text-clear",
  good: "text-clear",
  moderate: "text-moderate",
  marginal: "text-high-moderate",
}

// One plain-English sentence per band (D5 point 3) — anchored to the
// published US derivation-cohort distribution (median 12.8, IQR -0.8 to
// 27.2; 24% of donors score below 0) cited in
// app/reference_data/lkdpi_model.py, not re-derived here.
const LKDPI_BAND_SENTENCES = {
  excellent:
    "Below zero — lower risk than any deceased-donor kidney. About 24% of US living donors score in this range.",
  good: "Equivalent to a deceased-donor kidney better than the median — better than roughly half of deceased-donor kidneys.",
  moderate:
    "Equivalent to a deceased-donor kidney around the median deceased donor.",
  marginal:
    "Equivalent to a deceased-donor kidney worse than the median. About 4% of US living donors score above 50.",
}

function LKDPIScoreCard({ lkdpiResult }) {
  const [showAll, setShowAll] = useState(false)

  if (!lkdpiResult) return null

  if (!lkdpiResult.has_sufficient_data) {
    return (
      <Card>
        <p className="text-[14px] text-text">
          <span className="font-semibold">LKDPI not calculated.</span> Missing{" "}
          {lkdpiResult.missing_inputs.map((field, i) => (
            <span key={field}>
              {i > 0 && ", "}
              <span className="font-medium">{field}</span>
            </span>
          ))}
          . The score is withheld rather than estimated from a default — a compatibility index built on
          substituted values would look identical to one built on real ones.
        </p>
        <p className="text-[12px] text-text-muted mt-3 pt-3 border-t border-border">
          {lkdpiResult.model_limitation_note}
        </p>
      </Card>
    )
  }

  const bandTextClass = LKDPI_BAND_TEXT_CLASS[lkdpiResult.band] ?? "text-moderate"
  const badgeStatus = LKDPI_BAND_BADGE_STATUS[lkdpiResult.band] ?? "moderate"
  const contributions = lkdpiResult.contributions ?? []
  const maxAbs = Math.max(...contributions.map((c) => Math.abs(c.points)), 1)
  const shown = showAll ? contributions : contributions.slice(0, 5)

  return (
    <Card padded={false}>
      <div className="flex items-start gap-4 p-4 pb-3">
        <div>
          <p className={`text-[40px] font-extrabold tabular-nums leading-none ${bandTextClass}`}>
            {lkdpiResult.score > 0 ? "+" : ""}
            {lkdpiResult.score.toFixed(1)}
          </p>
          <p className="text-[11px] font-bold uppercase tracking-wide text-text-muted mt-1.5">LKDPI</p>
          <p className="text-[11px] text-text-muted">Living Kidney Donor Profile Index</p>
        </div>
        <div className="ml-auto">
          <Badge status={badgeStatus}>{lkdpiResult.band_label}</Badge>
        </div>
      </div>

      <p className="text-[13px] text-text px-4 pb-3">{LKDPI_BAND_SENTENCES[lkdpiResult.band]}</p>

      {lkdpiResult.single_factor_override && (
        <div className="mx-4 mb-3 rounded-md border border-moderate/30 bg-moderate-subtle p-3">
          <p className="text-[13px] text-moderate break-words">
            <span className="font-semibold">One factor is driving this score.</span>{" "}
            {lkdpiResult.single_factor_override.label} is{" "}
            {Math.abs(lkdpiResult.single_factor_override.delta).toFixed(2)} points{" "}
            {lkdpiResult.single_factor_override.delta > 0 ? "worse" : "better"} than a typical living
            donor — review this total with that in mind rather than reading it as settled.
          </p>
        </div>
      )}

      {!lkdpiResult.population_validated && lkdpiResult.population_extrapolation_disclaimer && (
        <div className="mx-4 mb-3 rounded-md border border-high-risk/30 bg-high-risk-subtle p-3">
          <p className="text-[13px] font-semibold text-high-risk">
            Extrapolated beyond the model's validated population
          </p>
          <p className="text-[13px] text-high-risk mt-1 break-words">
            {lkdpiResult.population_extrapolation_disclaimer}
          </p>
        </div>
      )}

      {lkdpiResult.values_outside_model_range?.length > 0 && (
        <div className="mx-4 mb-3 rounded-md border border-moderate/30 bg-moderate-subtle p-3">
          <p className="text-[13px] font-semibold text-moderate">
            Extrapolated beyond the model's checked input range
          </p>
          <ul className="list-disc list-inside text-[13px] text-moderate mt-1 space-y-0.5">
            {lkdpiResult.values_outside_model_range.map((flag) => (
              <li key={flag} className="break-words">
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="border-t border-border px-4 py-3">
        <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-2.5">
          <span>What moved this score from the baseline</span>
          <span>← better · worse →</span>
        </div>
        <div className="flex flex-col gap-2.5">
          {shown.map((c) => {
            const widthPct = (Math.abs(c.points) / maxAbs) * 50
            const positive = c.points >= 0
            return (
              <div key={c.label}>
                <div className="flex items-center justify-between gap-3 text-[12.5px] mb-1">
                  <span className="text-text break-words">{c.label}</span>
                  <span
                    className={`font-semibold tabular-nums shrink-0 ${
                      positive ? "text-high-moderate" : "text-clear"
                    }`}
                  >
                    {positive ? "+" : "−"}
                    {Math.abs(c.points).toFixed(2)}
                  </span>
                </div>
                <div className="relative h-[7px] rounded-full bg-bg border border-border">
                  <span
                    className="absolute top-1/2 left-1/2 -translate-y-1/2 w-px h-[11px] bg-border"
                    aria-hidden="true"
                  />
                  <span
                    className={`absolute top-0 bottom-0 rounded-full ${
                      positive ? "left-1/2 bg-high-moderate" : "right-1/2 bg-clear"
                    }`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {contributions.length > 5 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="w-full min-h-11 border-t border-border text-[12.5px] font-semibold text-accent"
        >
          {showAll ? "Show fewer" : `Show all ${contributions.length} factors`}
        </button>
      )}

      <div className="border-t border-border bg-bg px-4 py-3">
        <p className="text-[11.5px] text-text-muted leading-relaxed">
          <span className="font-semibold text-text">Model limitations.</span>{" "}
          {lkdpiResult.model_limitation_note}
        </p>
      </div>
    </Card>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between text-[14px]">
      <span className="text-text-muted">{label}</span>
      <span className="text-text font-medium tabular-nums break-words">{value}</span>
    </div>
  )
}

function MismatchBreakdown({ mismatchResult }) {
  return (
    <>
      <div className="flex flex-col gap-2 sm:hidden">
        {mismatchResult.locus_breakdown.map((row) => (
          <div key={row.locus} className="rounded-md border border-border p-3">
            <div className="flex items-center justify-between">
              <span className="font-medium text-text">{row.locus}</span>
              <Badge status={row.unique_mismatches > 0 ? "moderate" : "clear"}>
                {row.unique_mismatches} mismatch{row.unique_mismatches === 1 ? "" : "es"}
              </Badge>
            </div>
            <p className="text-[13px] text-text-muted mt-1 break-words">
              Patient: {row.patient_alleles.join(", ") || "—"}
            </p>
            <p className="text-[13px] text-text-muted break-words">
              Donor: {row.donor_alleles.join(", ") || "—"}
            </p>
          </div>
        ))}
      </div>
      <div className="hidden sm:block">
        <Table
          columns={[
            { key: "locus", label: "Locus" },
            { key: "patient", label: "Patient" },
            { key: "donor", label: "Donor" },
            { key: "mismatches", label: "Mismatches", align: "right" },
          ]}
          rows={mismatchResult.locus_breakdown}
          getRowId={(row) => row.locus}
          renderCell={(row, col) => {
            if (col.key === "patient") return row.patient_alleles.join(", ") || "—"
            if (col.key === "donor") return row.donor_alleles.join(", ") || "—"
            if (col.key === "mismatches") return row.unique_mismatches
            return row[col.key]
          }}
        />
      </div>
    </>
  )
}

// Builds the 7-row step timeline from the report's raw step results.
// Deliberately reads the raw fields (abo_result, mismatch_result, ...)
// rather than only the outcome, so every step's own pass/halt/flagged
// state is exactly what that step actually computed — the outcome decides
// the headline verdict, not what each individual step displays.
function buildSteps(report) {
  const steps = []

  steps.push({
    number: 1,
    name: "Step 1 — ABO compatibility",
    status: report.abo_result.is_compatible ? "pass" : "halt",
    summary: `Recipient ${report.abo_result.recipient_type} / donor ${report.abo_result.donor_type}`,
    detail: (
      <Row
        label="Recipient / donor blood type"
        value={`${report.abo_result.recipient_type} / ${report.abo_result.donor_type}`}
      />
    ),
  })

  if (report.sensitization_result) {
    steps.push({
      number: 2,
      name: "Step 2 — Sensitization",
      status: "pass",
      summary: "Computed for reference — not yet a reject/proceed gate",
      detail: (
        <div className="flex flex-col gap-2">
          <Row label="Total sensitization score" value={`${report.sensitization_result.total_score.toFixed(1)} pts`} />
          <Row
            label="Adjusted MFI cutoff"
            value={report.sensitization_result.adjusted_mfi_cutoff.toLocaleString()}
          />
        </div>
      ),
    })
  } else {
    steps.push(notReachedStep(2, "Step 2 — Sensitization"))
  }

  if (report.mismatch_result) {
    const incomplete = report.mismatch_result.data_completeness === false
    steps.push({
      number: 3,
      name: "Step 3 — HLA mismatches",
      status: report.mismatch_result.is_halted ? "halt" : incomplete ? "flagged" : "pass",
      summary: `${report.mismatch_result.total_mismatches} total (A/B/DRB1) — ${report.mismatch_result.bucket_name}`,
      detail: (
        <div className="flex flex-col gap-3">
          {incomplete && (
            <p className="text-[13px] text-moderate break-words">
              Incomplete typing — {report.mismatch_result.missing_inputs.join(", ")} missing. Missing loci
              are scored at their worst case rather than treated as a match, so this total is a
              conservative estimate, not a confirmed mismatch count.
            </p>
          )}
          <MismatchBreakdown mismatchResult={report.mismatch_result} />
        </div>
      ),
    })
  } else {
    steps.push(notReachedStep(3, "Step 3 — HLA mismatches"))
  }

  if (report.pra_bucket_result) {
    const highCpra = report.pra_bucket_result.bucket_name === ">60%"
    steps.push({
      number: 4,
      name: "Step 4 — PRA",
      status: highCpra ? "flagged" : "pass",
      summary: report.pra_bucket_result.has_sufficient_data
        ? `cPRA ${report.pra_bucket_result.percent.toFixed(1)}% — ${report.pra_bucket_result.bucket_name}`
        : "Not enough population data for a cPRA figure",
      detail: report.pra_bucket_result.has_sufficient_data ? (
        <Row
          label={`Calculated cPRA (bucket: ${report.pra_bucket_result.bucket_name})`}
          value={`${report.pra_bucket_result.percent.toFixed(1)}%`}
        />
      ) : (
        <p className="text-[14px] text-text-muted">
          Not enough population data yet to calculate a cPRA figure — this step passed without a
          bucketed result.
        </p>
      ),
    })
  } else {
    steps.push(notReachedStep(4, "Step 4 — PRA"))
  }

  if (report.dsa_result) {
    steps.push({
      number: 5,
      name: "Step 5 — DSA",
      status: report.dsa_result.is_halted ? "halt" : report.dsa_result.requires_review ? "flagged" : "pass",
      summary: report.dsa_result.is_halted
        ? "Strong donor-specific antibody detected"
        : report.dsa_result.requires_review
          ? "Weak/moderate DSA — flagged for desensitization review"
          : "No donor-specific antibody above the MFI floor",
      detail:
        report.dsa_result.matches.length > 0 ? (
          <div className="flex flex-col gap-2">
            {report.dsa_result.matches.map((match) => (
              <div key={match.antigen} className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between text-[14px]">
                <span className="text-text-muted break-words">
                  Anti-{match.antigen} (MFI {match.mfi.toLocaleString()})
                </span>
                <Badge status={match.severity === "strong" ? "high-risk" : "moderate"}>{match.severity}</Badge>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[14px] text-text-muted">No donor-specific antibody detected above the MFI floor.</p>
        ),
    })
  } else {
    steps.push(notReachedStep(5, "Step 5 — DSA"))
  }

  if (report.crossmatch_result) {
    steps.push({
      number: 6,
      name: "Step 6 — Crossmatch",
      status: report.crossmatch_result.is_halted ? "halt" : "pass",
      summary: report.crossmatch_result.is_positive ? "Positive" : "Negative",
      detail: (
        <div className="flex flex-col gap-2">
          <Row
            label="Result"
            value={report.crossmatch_result.is_positive ? "Positive" : "Negative"}
          />
          {report.crossmatch_result.t_cell_result && (
            <Row label="T-cell result" value={report.crossmatch_result.t_cell_result} />
          )}
          {report.crossmatch_result.b_cell_result && (
            <Row label="B-cell result" value={report.crossmatch_result.b_cell_result} />
          )}
          {report.crossmatch_result.remarks && <Row label="Remarks" value={report.crossmatch_result.remarks} />}
        </div>
      ),
    })
  } else if (report.overall_status === "pending_crossmatch") {
    steps.push({
      number: 6,
      name: "Step 6 — Crossmatch",
      status: "not-reached",
      summary: "Awaiting a submitted crossmatch result",
      detail: (
        <p className="text-[14px] text-text-muted break-words">
          Every gate through Step 5 (ABO, mismatches, DSA) passed, but no crossmatch result was
          submitted with this check. Submit one and re-run the check to reach Step 7.
        </p>
      ),
    })
  } else {
    steps.push(notReachedStep(6, "Step 6 — Crossmatch"))
  }

  if (report.overall_status === "completed") {
    const flagged = report.final_risk_level === null
    steps.push({
      number: 7,
      name: "Step 7 — Final risk classification",
      status: flagged ? "flagged" : "pass",
      summary: report.final_risk_level ?? "No agreed risk band for this cPRA range",
      detail: report.final_risk_level ? (
        <Row label="Combines the Step 3 mismatch bucket and Step 4 PRA bucket" value={report.final_risk_level} />
      ) : (
        <p className="text-[14px] text-moderate break-words">
          No doctor-specified point value exists yet for this cPRA range, so Step 7 can't combine a
          final risk level rather than guessing one. See Steps 5/6 (DSA, crossmatch) for this
          pairing's actual result.
        </p>
      ),
    })
  } else {
    steps.push(notReachedStep(7, "Step 7 — Final risk classification"))
  }

  return steps
}

function notReachedStep(number, name) {
  return {
    number,
    name,
    status: "not-reached",
    summary: "Not evaluated",
    detail: (
      <p className="text-[14px] text-text-muted break-words">
        Not evaluated — the check halted at an earlier step.
      </p>
    ),
  }
}

function StepTimeline({ report }) {
  const [openSteps, setOpenSteps] = useState(() => new Set())
  const steps = buildSteps(report)

  const toggle = (number) => {
    setOpenSteps((prev) => {
      const next = new Set(prev)
      if (next.has(number)) next.delete(number)
      else next.add(number)
      return next
    })
  }

  return (
    <Card padded={false}>
      <p className="text-[13px] font-semibold text-text-muted px-4 pt-4 pb-2">Pipeline steps</p>
      {steps.map((step) => {
        const isOpen = openSteps.has(step.number)
        const panelId = `step-panel-${step.number}`

        return (
          <div key={step.number} className="border-b border-border last:border-b-0">
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => toggle(step.number)}
              className="w-full min-h-11 flex items-center gap-3 px-4 py-3 text-left"
            >
              <span
                className={`h-6 w-6 shrink-0 rounded-full flex items-center justify-center text-[13px] font-bold ${STEP_MARKER_STYLES[step.status]}`}
                aria-hidden="true"
              >
                {STEP_MARKER_GLYPHS[step.status]}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={`block text-[14px] font-medium truncate ${
                    step.status === "not-reached" ? "text-text-muted" : "text-text"
                  }`}
                >
                  {step.name}
                </span>
                <span className="block text-[13px] text-text-muted truncate">{step.summary}</span>
              </span>
              <span
                className={`shrink-0 text-text-muted transition-transform ${isOpen ? "rotate-90" : ""}`}
                aria-hidden="true"
              >
                ›
              </span>
            </button>
            {isOpen && (
              <div id={panelId} className="px-4 pb-4 pl-[52px]">
                {step.detail}
              </div>
            )}
          </div>
        )
      })}
    </Card>
  )
}

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { markReviewed } = useReviewedReports()

  const [report, setReport] = useState(null)
  const [loadState, setLoadState] = useState("loading")

  useEffect(() => {
    let cancelled = false

    getReport(reportId)
      .then((data) => {
        if (cancelled) return
        setReport(data)
        setLoadState("loaded")
        markReviewed(reportId)
      })
      .catch(() => !cancelled && setLoadState("error"))

    return () => {
      cancelled = true
    }
  }, [reportId, markReviewed])

  if (loadState === "loading") {
    return (
      <div className="flex justify-center py-16">
        <div
          className="h-8 w-8 rounded-full border-2 border-border border-t-accent animate-spin"
          role="status"
          aria-label="Loading"
        />
      </div>
    )
  }

  if (loadState === "error" || !report) {
    return <p className="text-[15px] text-text-muted">Couldn't load this report.</p>
  }

  const { status: badgeStatus, label: badgeLabel } = reportBadgeProps(report)
  const outcome = report.outcome

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[19px] sm:text-[22px] font-bold text-text break-words">Compatibility report</h1>
          <p className="text-[14px] text-text-muted mt-0.5">{new Date(report.created_at).toLocaleString()}</p>
        </div>
        <div>
          <Badge status={badgeStatus}>{badgeLabel}</Badge>
        </div>
      </div>

      {outcome ? (
        <>
          <VerdictHero outcome={outcome} />
          <ActionStrip actionRequired={outcome.action_required} />
          <ReviewFlags flags={outcome.review_flags} />
          {/* No LKDPI at all for not_compatible — there's no point scoring
              a transplant that can't happen (see lkdpi_service.py). */}
          {outcome.verdict !== "not_compatible" && (
            <LKDPIScoreCard lkdpiResult={report.lkdpi_result} />
          )}
        </>
      ) : (
        <div className="rounded-lg border border-border bg-surface p-5">
          <p className="text-[15px] text-text-muted">
            This report was created before outcome summaries existed and hasn't been backfilled yet.
            See the step timeline below for the full result.
          </p>
        </div>
      )}

      <StepTimeline report={report} />

      <div className="flex justify-start pb-2">
        <Link to="/">
          <Button variant="secondary">Back to dashboard</Button>
        </Link>
      </div>
    </div>
  )
}
