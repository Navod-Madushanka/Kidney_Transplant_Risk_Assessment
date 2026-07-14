// src/pages/ReportDetailPage.jsx
import { useEffect, useState } from "react"
import { useParams, Link } from "react-router-dom"
import { getReport } from "../api/reports"
import { deriveRiskTier } from "../constants/riskTiers"
import { useReviewedReports } from "../hooks/useReviewedReports"
import Card from "../components/ui/Card"
import Badge from "../components/ui/Badge"
import Table from "../components/ui/Table"
import Button from "../components/ui/Button"

const RISK_TIER_TO_BADGE_STATUS = {
  "Low Risk": "low",
  "Moderate Risk": "moderate",
  "High-Moderate Risk": "high-moderate",
  "High Genetic Risk": "high-risk",
}

function HaltBanner({ report }) {
  if (report.overall_status === "halted_abo_fail") {
    return (
      <div className="rounded-md border border-high-risk/30 bg-high-risk-subtle p-4">
        <p className="text-[15px] font-semibold text-high-risk">ABO incompatible</p>
        <p className="text-[13px] text-text-muted mt-1">
          Recipient blood type {report.abo_result.recipient_type} is not compatible with
          donor type {report.abo_result.donor_type}. The check was halted before any
          further scoring ran.
        </p>
      </div>
    )
  }

  if (report.overall_status === "halted_dsa_trigger") {
    return (
      <div className="rounded-md border border-high-risk/30 bg-high-risk-subtle p-4 flex flex-col gap-2">
        <p className="text-[15px] font-semibold text-high-risk">
          Donor-specific antibody detected
        </p>
        {report.dsa_result.matches.map((match) => (
          <p key={match.antigen} className="text-[13px] text-text-muted">
            {match.warning_message}
          </p>
        ))}
      </div>
    )
  }

  return null
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

  const isHalted =
    report.overall_status === "halted_abo_fail" ||
    report.overall_status === "halted_dsa_trigger"
  const riskTier = deriveRiskTier(report.hla_scoring_result)

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-text">Compatibility report</h1>
          <p className="text-[14px] text-text-muted mt-0.5">
            {new Date(report.created_at).toLocaleString()}
          </p>
        </div>
        {isHalted ? (
          <Badge status={report.overall_status === "halted_abo_fail" ? "fail" : "halt"}>
            {report.overall_status === "halted_abo_fail" ? "ABO Fail" : "DSA Halt"}
          </Badge>
        ) : riskTier ? (
          <Badge status={RISK_TIER_TO_BADGE_STATUS[riskTier] ?? "neutral"}>{riskTier}</Badge>
        ) : (
          <Badge status="neutral">Completed</Badge>
        )}
      </div>

      {isHalted && <HaltBanner report={report} />}

      <Card>
        <Card.Header title="ABO compatibility" />
        <div className="flex items-center justify-between text-[14px]">
          <span className="text-text-muted">Recipient / donor blood type</span>
          <span className="text-text font-medium tabular-nums">
            {report.abo_result.recipient_type} / {report.abo_result.donor_type}
          </span>
        </div>
      </Card>

      {report.sensitization_result && (
        <Card>
          <Card.Header title="Sensitization" />
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

      {report.hla_scoring_result && (
        <Card>
          <Card.Header
            title="HLA mismatch scoring"
            subtitle={`Total: ${report.hla_scoring_result.total_score.toFixed(2)} points`}
          />
          <HlaBreakdownTable hlaScoringResult={report.hla_scoring_result} />
        </Card>
      )}

      {report.cpra_result && (
        <Card>
          <Card.Header title="cPRA" />
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

      <div className="flex justify-start">
        <Link to="/">
          <Button variant="secondary">Back to dashboard</Button>
        </Link>
      </div>
    </div>
  )
}