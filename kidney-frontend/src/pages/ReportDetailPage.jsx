// src/pages/ReportDetailPage.jsx
import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { getReport } from "../api/reports"
import { deriveRiskTier } from "../constants/riskTiers"
import {
  HALTED_STATUSES,
  HALT_DESCRIPTIONS,
  PENDING_CROSSMATCH_STATUS,
  reportBadgeProps,
} from "../constants/reportStatus"
import { useReviewedReports } from "../hooks/useReviewedReports"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Table from "../components/ui/Table"
import Button from "../components/ui/Button"

function HaltBanner({ report }) {
  const status = report.overall_status

  if (status === PENDING_CROSSMATCH_STATUS) {
    return (
      <div className="rounded-md border border-border bg-bg p-4">
        <p className="text-[15px] font-semibold text-text">Awaiting crossmatch</p>
        <p className="text-[13px] text-text-muted mt-1">
          Every gate through Step 5 (ABO, mismatches, PRA, DSA) passed, but no crossmatch
          result was submitted with this check, so the final risk classification hasn't run.
          Run a new compatibility check for this pair once a crossmatch result is available.
        </p>
      </div>
    )
  }

  if (!HALTED_STATUSES.has(status)) return null

  return (
    <div className="rounded-md border border-high-risk/30 bg-high-risk-subtle p-4 flex flex-col gap-2">
      <p className="text-[15px] font-semibold text-high-risk">{HALT_DESCRIPTIONS[status]}</p>

      {status === "halted_abo_fail" && (
        <p className="text-[13px] text-text-muted">
          Recipient blood type {report.abo_result.recipient_type} is not compatible with
          donor type {report.abo_result.donor_type}. The check was halted before any further
          scoring ran.
        </p>
      )}

      {status === "halted_dsa_trigger" &&
        report.dsa_result.matches.map((match) => (
          <p key={match.antigen} className="text-[13px] text-text-muted">
            {match.warning_message}
          </p>
        ))}

      {status === "halted_mismatch_reject" && (
        <p className="text-[13px] text-text-muted">
          {report.mismatch_result.total_mismatches} HLA mismatches across A/B/DRB1 (bucket:{" "}
          {report.mismatch_result.bucket_name}) — above the acceptable threshold for Step 3.
        </p>
      )}

      {status === "halted_pra_reject" && (
        <p className="text-[13px] text-text-muted">
          Calculated cPRA of {report.pra_bucket_result.percent.toFixed(1)}% (bucket:{" "}
          {report.pra_bucket_result.bucket_name}) — above the acceptable threshold for Step 4.
        </p>
      )}

      {status === "halted_crossmatch_positive" && (
        <div className="text-[13px] text-text-muted flex flex-col gap-0.5">
          <span>Positive crossmatch — patient serum reacted against donor cells.</span>
          {report.crossmatch_result.t_cell_result && (
            <span>T-cell: {report.crossmatch_result.t_cell_result}</span>
          )}
          {report.crossmatch_result.b_cell_result && (
            <span>B-cell: {report.crossmatch_result.b_cell_result}</span>
          )}
          {report.crossmatch_result.remarks && <span>{report.crossmatch_result.remarks}</span>}
        </div>
      )}
    </div>
  )
}

function HlaBreakdownTable({ hlaScoringResult }) {
  return (
    <Table
      columns={[
        { key: "locus", label: "Locus" },
        { key: "mismatches", label: "Mismatches", align: "right" },
        { key: "weight", label: "Weight", align: "right" },
        { key: "points", label: "Points", align: "right" },
      ]}
      rows={hlaScoringResult.locus_breakdown}
      getRowId={(row) => row.locus}
      renderCell={(row, col) => {
        if (col.key === "mismatches") return row.unique_mismatches
        if (col.key === "weight") return row.weight.toFixed(2)
        if (col.key === "points") return row.points.toFixed(2)
        return row[col.key]
      }}
    />
  )
}

function MismatchBreakdownTable({ mismatchResult }) {
  return (
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

  // The API doesn't return a `risk_tier` field (it was never persisted —
  // see kidney-backend/app/services/dashboard_service.py's _derive_risk_tier
  // docstring), so the legacy tier is re-derived client-side here, same as
  // before Step 7 existed. Folded into reportBadgeProps as a fallback for
  // when Step 7 has no final_risk_level yet (e.g. insufficient cPRA data).
  const legacyRiskTier = deriveRiskTier(report.hla_scoring_result)
  const { status: badgeStatus, label: badgeLabel } = reportBadgeProps({
    ...report,
    risk_tier: legacyRiskTier,
  })

  const isCompleted = report.overall_status === "completed"

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-text">Compatibility report</h1>
          <p className="text-[14px] text-text-muted mt-0.5">
            {new Date(report.created_at).toLocaleString()}
          </p>
        </div>
        <Badge status={badgeStatus}>{badgeLabel}</Badge>
      </div>

      <HaltBanner report={report} />

      <Card>
        <Card.Header title="Step 1 — ABO compatibility" />
        <div className="flex items-center justify-between text-[14px]">
          <span className="text-text-muted">Recipient / donor blood type</span>
          <span className="text-text font-medium tabular-nums">
            {report.abo_result.recipient_type} / {report.abo_result.donor_type}
          </span>
        </div>
      </Card>

      {report.sensitization_result && (
        <Card>
          <Card.Header
            title="Step 2 — Sensitization"
            subtitle="Computed for reference — not yet a reject/proceed gate"
          />
          <div className="flex items-center justify-between text-[14px]">
            <span className="text-text-muted">Total sensitization score</span>
            <span className="text-text font-medium tabular-nums">
              {report.sensitization_result.total_score.toFixed(1)} pts
            </span>
          </div>
          <div className="flex items-center justify-between text-[14px] mt-1">
            <span className="text-text-muted">Adjusted MFI cutoff</span>
            <span className="text-text font-medium tabular-nums">
              {report.sensitization_result.adjusted_mfi_cutoff.toLocaleString()}
            </span>
          </div>
        </Card>
      )}

      {report.mismatch_result && (
        <Card>
          <Card.Header
            title="Step 3 — HLA mismatches"
            subtitle={`${report.mismatch_result.total_mismatches} total (A/B/DRB1 only) — bucket: ${report.mismatch_result.bucket_name}`}
          />
          {report.mismatch_result.data_completeness === false && (
            <p className="text-[13px] text-high-risk mb-2">
              Incomplete typing — A/B/DRB1 typing is missing on at least one side of this pair.
              Missing loci are scored at their worst case rather than treated as a match, so this
              total is a conservative estimate, not a confirmed mismatch count.
            </p>
          )}
          <MismatchBreakdownTable mismatchResult={report.mismatch_result} />
        </Card>
      )}

      {report.pra_bucket_result && (
        <Card>
          <Card.Header title="Step 4 — PRA" />
          {report.pra_bucket_result.has_sufficient_data ? (
            <div className="flex items-center justify-between text-[14px]">
              <span className="text-text-muted">Calculated cPRA (bucket: {report.pra_bucket_result.bucket_name})</span>
              <span className="text-text font-medium tabular-nums">
                {report.pra_bucket_result.percent.toFixed(1)}%
              </span>
            </div>
          ) : (
            <p className="text-[14px] text-text-muted">
              Not enough population data yet to calculate a cPRA figure — this step passed
              without a bucketed result.
            </p>
          )}
        </Card>
      )}

      {report.dsa_result && (
        <Card>
          <Card.Header title="Step 5 — DSA" />
          {report.dsa_result.is_halted ? (
            <p className="text-[14px] text-high-risk font-medium">Donor-specific antibody detected — see banner above.</p>
          ) : (
            <p className="text-[14px] text-text-muted">
              No donor-specific antibody detected above the MFI threshold.
            </p>
          )}
        </Card>
      )}

      {report.crossmatch_result && (
        <Card>
          <Card.Header title="Step 6 — Crossmatch" />
          <div className="flex items-center justify-between text-[14px]">
            <span className="text-text-muted">Result</span>
            <span className={`font-medium ${report.crossmatch_result.is_positive ? "text-high-risk" : "text-clear"}`}>
              {report.crossmatch_result.is_positive ? "Positive" : "Negative"}
            </span>
          </div>
          {report.crossmatch_result.t_cell_result && (
            <div className="flex items-center justify-between text-[14px] mt-1">
              <span className="text-text-muted">T-cell result</span>
              <span className="text-text font-medium">{report.crossmatch_result.t_cell_result}</span>
            </div>
          )}
          {report.crossmatch_result.b_cell_result && (
            <div className="flex items-center justify-between text-[14px] mt-1">
              <span className="text-text-muted">B-cell result</span>
              <span className="text-text font-medium">{report.crossmatch_result.b_cell_result}</span>
            </div>
          )}
          {report.crossmatch_result.remarks && (
            <div className="flex items-center justify-between text-[14px] mt-1">
              <span className="text-text-muted">Remarks</span>
              <span className="text-text font-medium">{report.crossmatch_result.remarks}</span>
            </div>
          )}
        </Card>
      )}

      {isCompleted && (
        <Card>
          <Card.Header title="Step 7 — Final risk classification" />
          {report.final_risk_level ? (
            <div className="flex items-center justify-between text-[14px]">
              <span className="text-text-muted">
                Combines the Step 3 mismatch bucket and Step 4 PRA bucket
              </span>
              <Badge status={badgeStatus}>{report.final_risk_level}</Badge>
            </div>
          ) : report.mismatch_result?.data_completeness === false ? (
            <p className="text-[14px] text-high-risk font-medium">
              Cannot assess — A/B/DRB1 HLA typing is incomplete for this patient/donor pair, so
              Step 7 can't combine a reliable mismatch bucket rather than guessing one.
            </p>
          ) : (
            <p className="text-[14px] text-text-muted">
              No final classification yet — Step 4 didn't have enough population data for a
              PRA bucket, so Step 7 can't combine a result rather than guessing one.
            </p>
          )}
        </Card>
      )}

      {(report.hla_scoring_result || report.cpra_result) && (
        <div className="flex flex-col gap-6 pt-2 border-t border-border">
          <p className="text-[13px] font-semibold text-text-muted -mb-2">
            Legacy scoring (reference only — superseded by Steps 3/4/7 above)
          </p>

          {report.hla_scoring_result && (
            <Card>
              <Card.Header
                title="HLA mismatch scoring (legacy, all 9 loci)"
                subtitle={`Total: ${report.hla_scoring_result.total_score.toFixed(2)} points`}
              />
              <HlaBreakdownTable hlaScoringResult={report.hla_scoring_result} />
            </Card>
          )}

          {report.cpra_result && (
            <Card>
              <Card.Header title="cPRA (legacy)" />
              {report.cpra_result.has_sufficient_data ? (
                <div className="flex items-center justify-between text-[14px]">
                  <span className="text-text-muted">
                    Calculated cPRA (sample size {report.cpra_result.sample_size})
                  </span>
                  <span className="text-text font-medium tabular-nums">
                    {report.cpra_result.cpra_percentage.toFixed(1)}%
                  </span>
                </div>
              ) : (
                <p className="text-[14px] text-text-muted">{report.cpra_result.message}</p>
              )}
            </Card>
          )}
        </div>
      )}

      <div className="flex justify-start">
        <Link to="/">
          <Button variant="secondary">Back to dashboard</Button>
        </Link>
      </div>
    </div>
  )
}
