import { cn } from "@/lib/utils"
import { formatWorkflowId } from "@/lib/format"
import type { FunnelStage } from "@/lib/funnelStages"

function fmtNum(n: number): string {
  return n.toLocaleString()
}

export function RunCardMetrics({
  papersFound,
  papersIncluded,
  funnelStages,
  cost,
  workflowId,
  copiedWorkflowId,
  onCopyWorkflowId,
}: {
  papersFound?: number | null
  papersIncluded?: number | null
  funnelStages?: FunnelStage[]
  cost?: number | null
  workflowId?: string | null
  copiedWorkflowId?: string | null
  onCopyWorkflowId?: (id: string) => void | Promise<void>
}) {
  const hasFunnel = funnelStages != null && funnelStages.length > 0
  const hasStats =
    hasFunnel ||
    papersFound != null ||
    papersIncluded != null ||
    (cost != null && cost > 0)
  const hasWfId = workflowId != null && workflowId.length > 0

  if (!hasStats && !hasWfId) return null

  return (
    <div className="flex justify-between items-start gap-x-2 min-w-0 text-meta w-full">
      <div className="flex flex-col gap-y-0.5 min-w-0">
        {hasFunnel ? (
          funnelStages!.map((stage) => (
            <span key={stage.key} className="flex items-baseline gap-1 leading-none">
              <span className={cn("font-semibold tabular-nums", stage.colorClass)}>
                {fmtNum(stage.count)}
              </span>
              <span className="text-muted font-normal">{stage.label}</span>
            </span>
          ))
        ) : (
          <>
            {papersFound != null && (
              <span className="flex items-baseline gap-1 leading-none">
                <span className="font-semibold tabular-nums text-intent-info">{fmtNum(papersFound)}</span>
                <span className="text-muted font-normal">found</span>
              </span>
            )}
            {papersIncluded != null && (
              <span className="flex items-baseline gap-1 leading-none">
                <span className="font-semibold tabular-nums text-intent-success">{fmtNum(papersIncluded)}</span>
                <span className="text-muted font-normal">included</span>
              </span>
            )}
          </>
        )}
      </div>

      <div className="flex flex-col items-end gap-y-0.5 shrink-0">
        {cost != null && cost > 0 && (
          <span className="font-semibold text-intent-warning whitespace-nowrap">
            ${cost.toFixed(3)}
          </span>
        )}
        {hasWfId && (
          onCopyWorkflowId ? (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation()
                void onCopyWorkflowId(workflowId!)
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.stopPropagation()
                  void onCopyWorkflowId(workflowId!)
                }
              }}
              className="text-muted whitespace-nowrap hover:text-foreground transition-colors cursor-pointer"
              title="Copy workflow ID"
            >
              {copiedWorkflowId === workflowId ? "Copied!" : formatWorkflowId(workflowId!)}
            </span>
          ) : (
            <span
              className="text-muted whitespace-nowrap"
              title={workflowId ?? undefined}
            >
              {formatWorkflowId(workflowId!)}
            </span>
          )
        )}
      </div>
    </div>
  )
}
