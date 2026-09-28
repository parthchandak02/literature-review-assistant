import { ConfirmDialog } from "@/components/ConfirmDialog"
import { formatUsd } from "@/components/cost-ops/costOpsFormatters"
import { phaseLabel } from "@/lib/constants"
import { phasesRerunFrom, priorCostForPhases } from "@/lib/activityPhaseState"

export interface ResumeConfirmDialogProps {
  phase: string | null
  costByPhase: ReadonlyArray<{ phase: string; cost_usd: number }> | null
  costLoading?: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (phase: string) => Promise<void>
}

export function ResumeConfirmDialog({
  phase,
  costByPhase,
  costLoading = false,
  onOpenChange,
  onConfirm,
}: ResumeConfirmDialogProps) {
  const rerun = phase ? phasesRerunFrom(phase) : []
  const priorCost = priorCostForPhases(costByPhase, rerun)

  let costLine: string | null = null
  if (costLoading) costLine = "Loading the cost of the last attempt…"
  else if (priorCost !== null && priorCost > 0) {
    costLine = `Previously spent on these phases: ${formatUsd(priorCost)}.`
  }

  return (
    <ConfirmDialog
      open={phase !== null}
      onOpenChange={onOpenChange}
      title={phase ? `Resume from ${phaseLabel(phase, "long")}?` : "Resume run?"}
      confirmLabel="Resume run"
      pendingLabel="Resuming…"
      confirmVariant="default"
      onConfirm={async () => {
        if (phase) await onConfirm(phase)
      }}
      description={
        <span className="flex flex-col gap-2">
          <span>These phases will run again:</span>
          <span className="flex flex-col gap-0.5 pl-4" role="list" aria-label="Phases that will re-run">
            {rerun.map((id) => (
              <span key={id} role="listitem" className="list-item list-disc text-foreground">
                {phaseLabel(id, "long")}
              </span>
            ))}
          </span>
          {costLine ? <span data-testid="resume-prior-cost">{costLine}</span> : null}
        </span>
      }
    />
  )
}
