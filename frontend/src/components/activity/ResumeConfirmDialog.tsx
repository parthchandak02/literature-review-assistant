import { ConfirmDialog } from "@/components/ConfirmDialog"
import { formatUsd } from "@/components/cost-ops/costOpsFormatters"
import { milestoneForPhase, phaseLabel } from "@/lib/constants"
import { phasesRerunFrom, priorCostForPhases } from "@/lib/activityPhaseState"

export interface ResumeConfirmDialogProps {
  phase: string | null
  costByPhase: ReadonlyArray<{ phase: string; cost_usd: number }> | null
  costLoading?: boolean
  onOpenChange: (open: boolean) => void
  onConfirm: (phase: string) => Promise<void>
}

interface MilestonePhaseGroup {
  key: string
  milestone: string
  phases: string[]
}

function labelsOverlap(a: string, b: string): boolean {
  const x = a.trim().toLowerCase()
  const y = b.trim().toLowerCase()
  return x.includes(y) || y.includes(x)
}

// eslint-disable-next-line react-refresh/only-export-components -- pure helper tested alongside the dialog
export function groupPhasesByMilestone(phases: readonly string[]): MilestonePhaseGroup[] {
  const groups: MilestonePhaseGroup[] = []
  for (const id of phases) {
    const milestone = milestoneForPhase(id)
    const key = milestone?.key ?? id
    const label = phaseLabel(id, "long")
    const last = groups[groups.length - 1]
    if (last && last.key === key) last.phases.push(label)
    else groups.push({ key, milestone: milestone?.label ?? label, phases: [label] })
  }
  return groups.map((group) => {
    if (group.phases.length !== 1 || !labelsOverlap(group.milestone, group.phases[0])) return group
    const [only] = group.phases
    return { ...group, milestone: only.length > group.milestone.length ? only : group.milestone, phases: [] }
  })
}

export function ResumeConfirmDialog({
  phase,
  costByPhase,
  costLoading = false,
  onOpenChange,
  onConfirm,
}: ResumeConfirmDialogProps) {
  const rerun = phase ? phasesRerunFrom(phase) : []
  const groups = groupPhasesByMilestone(rerun)
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
          <span>These stages will run again:</span>
          <span className="flex flex-col gap-0.5 pl-4" role="list" aria-label="Phases that will re-run">
            {groups.map((group) => (
              <span key={group.key} role="listitem" className="list-item list-disc text-foreground">
                <span className="font-medium">{group.milestone}</span>
                {group.phases.length > 0 && <span className="text-muted">: {group.phases.join(", ")}</span>}
              </span>
            ))}
          </span>
          {costLine ? <span data-testid="resume-prior-cost">{costLine}</span> : null}
        </span>
      }
    />
  )
}
