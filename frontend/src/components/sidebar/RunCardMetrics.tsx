import { Check, ChevronDown, Copy } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatCount as fmtNum, formatWorkflowId } from "@/lib/format"
import { resolveSummaryCounts, type RunCardMetricsInput } from "@/components/sidebar/historyRowModel"

export function RunCardDetailsToggle({
  expanded,
  onToggle,
  label,
  controlsId,
}: {
  expanded: boolean
  onToggle: () => void
  label: string | null
  controlsId: string
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      aria-controls={controlsId}
      aria-label={label ? `${label}. ${expanded ? "Hide" : "Show"} details` : `${expanded ? "Hide" : "Show"} details`}
      className="relative z-10 inline-flex min-w-0 items-center gap-0.5 rounded-control px-1 -mx-1 text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {label && <span className="truncate font-medium tabular-nums">{label}</span>}
      <ChevronDown
        className={cn("h-3 w-3 shrink-0 transition-transform", expanded && "rotate-180")}
        aria-hidden
      />
    </button>
  )
}

export function RunCardDetails({
  id,
  papersFound,
  papersIncluded,
  funnelStages,
  cost,
  workflowId,
  copiedWorkflowId,
  onCopyWorkflowId,
}: RunCardMetricsInput & {
  id: string
  workflowId?: string | null
  copiedWorkflowId?: string | null
  onCopyWorkflowId?: (id: string) => void | Promise<void>
}) {
  const { found, included } = resolveSummaryCounts(papersFound, papersIncluded, funnelStages)
  const hasFunnel = funnelStages != null && funnelStages.length > 0
  const searchRan = found != null && found > 0
  const copied = workflowId != null && copiedWorkflowId === workflowId

  return (
    <div id={id} className="flex items-start justify-between gap-2 min-w-0 text-meta">
      <div className="flex flex-col gap-y-0.5 min-w-0">
        {hasFunnel
          ? funnelStages!.map((stage) => (
              <div key={stage.key} className="flex items-baseline gap-1 leading-none">
                <span className={cn("font-semibold tabular-nums", stage.colorClass)}>{fmtNum(stage.count)}</span>
                <span className="text-muted">{stage.label}</span>
              </div>
            ))
          : searchRan && (
              <>
                <div className="flex items-baseline gap-1 leading-none">
                  <span className="font-semibold tabular-nums text-intent-info">{fmtNum(found!)}</span>
                  <span className="text-muted">found</span>
                </div>
                {included != null && (
                  <div className="flex items-baseline gap-1 leading-none">
                    <span className="font-semibold tabular-nums text-intent-success">{fmtNum(included)}</span>
                    <span className="text-muted">included</span>
                  </div>
                )}
              </>
            )}
        {cost != null && cost > 0 && (
          <div className="flex items-baseline gap-1 leading-none">
            <span className="font-semibold tabular-nums text-intent-warning">${cost.toFixed(3)}</span>
            <span className="text-muted">cost</span>
          </div>
        )}
      </div>
      {workflowId && onCopyWorkflowId && (
        <button
          type="button"
          onClick={() => void onCopyWorkflowId(workflowId)}
          aria-label={copied ? "Workflow ID copied" : `Copy workflow ID ${formatWorkflowId(workflowId)}`}
          className="relative z-10 inline-flex shrink-0 items-center gap-1 rounded-control px-1 text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
          <span className="tabular-nums">{copied ? "Copied" : formatWorkflowId(workflowId)}</span>
        </button>
      )}
    </div>
  )
}
