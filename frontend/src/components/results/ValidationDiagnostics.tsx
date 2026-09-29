import { useState } from "react"
import { ChevronRight, ClipboardCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsBlock } from "@/components/ui/section"
import { humanizeIdentifier, humanizeStatus } from "@/lib/humanize"
import { phaseLabel } from "@/lib/constants"
import { useDbCostDashboard, useWorkflowValidationSummaryWithChecks } from "@/hooks/useDbCosts"
import type { ScreeningDiagnostics } from "@/lib/api"
import { cn } from "@/lib/utils"
import { QualityStatusBadge } from "./QualityStatusBadge"
import { validationCheckTitle, validationStatusStyle } from "./qualityStatus"

export const VALIDATION_CHECKS_PREVIEW = 8

function StatusBadge({ status }: { status: string }) {
  return <QualityStatusBadge variant={validationStatusStyle(status).variant} label={humanizeStatus(status)} />
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="label-muted truncate">{label}</dt>
      <dd className="text-sm text-foreground tabular-nums">{value}</dd>
    </div>
  )
}

export interface ValidationDiagnosticsProps {
  /** Run id; used for screening diagnostics from the cost dashboard. */
  runId: string | null | undefined
  /** Workflow id; validation summaries are keyed by workflow. */
  workflowId: string | null | undefined
  className?: string
}

const PROFILE_TITLES: Record<string, string> = {
  pre_writing_gate: "Pre-writing validation",
}

function validationTitle(profile: string | null | undefined): string {
  if (!profile) return "Validation"
  return PROFILE_TITLES[profile] ?? `${humanizeIdentifier(profile).replace(/^Pre writing\b/, "Pre-writing")} validation`
}

const SCREENING_COUNTERS: { key: keyof ScreeningDiagnostics; label: string }[] = [
  { key: "batch_parse_degraded", label: "Screening batches whose AI reply could not be read" },
  { key: "batch_id_mismatch", label: "AI replies that named the wrong paper" },
  { key: "batch_missing_fallback", label: "Papers re-screened one at a time after a batch skipped them" },
  { key: "contract_violation_count", label: "Screening replies in the wrong format" },
]

function ScreeningTechnicalDetails({ screening }: { screening: ScreeningDiagnostics }) {
  const [open, setOpen] = useState(false)
  const problems = SCREENING_COUNTERS.reduce((sum, c) => sum + (Number(screening[c.key]) || 0), 0)
  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="self-start px-0 hover:bg-transparent"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronRight aria-hidden className={cn("transition-transform", open && "rotate-90")} />
        Technical details
        <span className="text-muted font-normal">
          {problems === 0 ? "· no screening output problems" : `· ${problems} screening output problems`}
        </span>
      </Button>
      {open && (
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SCREENING_COUNTERS.map((c) => (
            <Stat key={c.key} label={c.label} value={screening[c.key]} />
          ))}
        </dl>
      )}
    </div>
  )
}

export function ValidationDiagnostics({ runId, workflowId, className }: ValidationDiagnosticsProps) {
  const [showAll, setShowAll] = useState(false)
  const dashboardQuery = useDbCostDashboard(runId, { enabled: Boolean(runId) })
  const validationQuery = useWorkflowValidationSummaryWithChecks(workflowId)

  const summary = validationQuery.data?.latest_run ?? null
  const checks = validationQuery.data?.checks ?? []
  const screening = dashboardQuery.data?.screening_diagnostics ?? null

  if (!summary && !screening && checks.length === 0) return null

  const visibleChecks = showAll ? checks : checks.slice(0, VALIDATION_CHECKS_PREVIEW)
  const hiddenCount = checks.length - visibleChecks.length
  const phases = new Set(checks.map((c) => c.phase))
  const sharedPhase = phases.size === 1 ? checks[0]?.phase : null
  const groupTitle = sharedPhase ? phaseLabel(sharedPhase) : "Latest validation checks"

  return (
    <ResultsBlock icon={ClipboardCheck} title={validationTitle(summary?.profile)} className={className}>
      {summary && (
        <>
          <p className="text-xs text-muted">Run before the manuscript was written. The final manuscript checks are above.</p>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Result" value={<StatusBadge status={summary.status} />} />
            <Stat label="Checks run" value={summary.total_checks ?? checks.length} />
            <Stat label="Errors" value={summary.error_count} />
            <Stat label="Warnings" value={summary.warn_count} />
          </dl>
        </>
      )}

      {checks.length > 0 && (
        <div className="overflow-hidden rounded-panel border border-border">
          <div className="border-b border-border px-3 py-2 text-xs font-semibold text-muted">
            {groupTitle} ({checks.length})
          </div>
          <ul className="divide-y divide-border">
            {visibleChecks.map((check, idx) => (
              <li
                key={`${check.phase}-${check.check_name}-${idx}`}
                className="px-3 py-2 text-xs"
                title={[check.check_name, check.source_module].filter(Boolean).join(" · ")}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-foreground">{validationCheckTitle(check.check_name)}</span>
                  <StatusBadge status={check.status} />
                </div>
                {(!sharedPhase || check.metric_value != null) && (
                  <div className="mt-0.5 text-muted">
                    {!sharedPhase && phaseLabel(check.phase)}
                    {!sharedPhase && check.metric_value != null && " · "}
                    {check.metric_value != null && (
                      <>
                        metric <span className="tabular-nums">{check.metric_value}</span>
                      </>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          {checks.length > VALIDATION_CHECKS_PREVIEW && (
            <div className="border-t border-border px-2 py-1">
              <Button type="button" variant="ghost" size="xs" onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show fewer" : `Show all ${checks.length} (${hiddenCount} more)`}
              </Button>
            </div>
          )}
        </div>
      )}

      {screening && <ScreeningTechnicalDetails screening={screening} />}
    </ResultsBlock>
  )
}
