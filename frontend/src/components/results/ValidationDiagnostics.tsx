import { useState } from "react"
import { AlertTriangle, CheckCircle2, CircleDashed, ClipboardCheck, XCircle } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Badge, type BadgeVariant } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ResultsBlock } from "@/components/ui/section"
import { humanizeSnake, humanizeStatus } from "@/lib/humanize"
import { phaseLabel } from "@/lib/constants"
import { useDbCostDashboard, useWorkflowValidationSummaryWithChecks } from "@/hooks/useDbCosts"

export const VALIDATION_CHECKS_PREVIEW = 8

interface StatusStyle {
  variant: BadgeVariant
  icon: LucideIcon
}

// eslint-disable-next-line react-refresh/only-export-components
export function validationStatusStyle(status: string | null | undefined): StatusStyle {
  const s = (status ?? "").toLowerCase()
  if (s === "error" || s === "fail" || s === "failed") return { variant: "danger", icon: XCircle }
  if (s === "warn" || s === "warning") return { variant: "warning", icon: AlertTriangle }
  if (s === "pass" || s === "passed" || s === "ok" || s === "success") return { variant: "success", icon: CheckCircle2 }
  return { variant: "neutral", icon: CircleDashed }
}

function StatusBadge({ status }: { status: string }) {
  const { variant, icon: Icon } = validationStatusStyle(status)
  return (
    <Badge variant={variant} size="sm">
      <Icon aria-hidden />
      {humanizeStatus(status)}
    </Badge>
  )
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

  return (
    <ResultsBlock icon={ClipboardCheck} title="Validation and screening diagnostics" className={className}>
      {summary && (
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Validation status" value={<StatusBadge status={summary.status} />} />
          <Stat label="Profile" value={humanizeSnake(summary.profile)} />
          <Stat label="Error checks" value={summary.error_count} />
          <Stat label="Warning checks" value={summary.warn_count} />
        </dl>
      )}

      {checks.length > 0 && (
        <div className="overflow-hidden rounded-panel border border-border">
          <div className="border-b border-border px-3 py-2 text-xs font-semibold text-muted">
            Latest validation checks ({checks.length})
          </div>
          <ul className="divide-y divide-border">
            {visibleChecks.map((check, idx) => (
              <li key={`${check.phase}-${check.check_name}-${idx}`} className="px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-foreground" title={check.check_name}>
                    {humanizeSnake(check.check_name)}
                  </span>
                  <StatusBadge status={check.status} />
                </div>
                <div className="mt-0.5 text-muted">
                  {phaseLabel(check.phase)}
                  {check.metric_value != null && <> · metric <span className="tabular-nums">{check.metric_value}</span></>}
                  {check.source_module && <> · {check.source_module}</>}
                </div>
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

      {screening && (
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Batch parse degraded" value={screening.batch_parse_degraded} />
          <Stat label="Batch id mismatch" value={screening.batch_id_mismatch} />
          <Stat label="Missing fallback" value={screening.batch_missing_fallback} />
          <Stat label="Contract violations" value={screening.contract_violation_count} />
        </dl>
      )}
    </ResultsBlock>
  )
}
