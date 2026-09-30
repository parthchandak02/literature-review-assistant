import { Check, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatCount as fmtNum, formatWorkflowId } from "@/lib/format"
import type { LiveRun } from "@/components/sidebar/types"
import {
  formatCardCost,
  runCardSummaryText,
  type RunCardSummary,
} from "@/components/sidebar/historyRowModel"

const inlineControl =
  "touch-hit relative z-10 inline-flex shrink-0 items-center gap-0.5 rounded-control px-1 -mx-1 pointer-coarse:min-h-6 text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

/** Always-visible fact row: found to included, cost, and the copyable workflow id. */
export function RunCardMetricRow({
  summary,
  workflowId,
  copiedWorkflowId,
  onCopyWorkflowId,
  funnel,
}: {
  summary: RunCardSummary
  workflowId?: string | null
  copiedWorkflowId?: string | null
  onCopyWorkflowId?: (id: string) => void | Promise<void>
  funnel?: { expanded: boolean; onToggle: () => void; controlsId: string }
}) {
  const { found, included, cost } = summary
  const countsText = runCardSummaryText(summary)
  const copied = workflowId != null && copiedWorkflowId === workflowId
  const wfLabel = formatWorkflowId(workflowId)

  return (
    <div className="flex min-w-0 items-center gap-2 text-2xs">
      {found != null && (
        <span className="num min-w-0 truncate" title={countsText ?? undefined}>
          <span aria-hidden>
            <span className="font-semibold text-intent-info-text">{fmtNum(found)}</span>
            {included != null ? (
              <>
                <span className="text-muted"> → </span>
                <span className={cn("font-semibold", included > 0 ? "text-intent-success-text" : "text-muted")}>
                  {fmtNum(included)}
                </span>
                <span className="text-muted"> incl</span>
              </>
            ) : (
              <span className="text-muted"> found</span>
            )}
          </span>
          <span className="sr-only">{countsText}</span>
        </span>
      )}
      {cost != null && (
        <span className="num shrink-0 text-foreground" title={`Cost $${cost.toFixed(3)}`}>
          <span className="sr-only">Cost </span>
          {formatCardCost(cost)}
        </span>
      )}
      {(wfLabel || funnel) && (
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {wfLabel && (
            onCopyWorkflowId ? (
              <button
                type="button"
                onClick={() => void onCopyWorkflowId(workflowId!)}
                aria-label={copied ? "Workflow ID copied" : `Copy workflow ID ${wfLabel}`}
                title="Copy workflow ID"
                className={cn(inlineControl, "num")}
              >
                {copied && <Check className="h-3 w-3" aria-hidden />}
                {copied ? "Copied" : wfLabel}
              </button>
            ) : (
              <span className="num text-muted">{wfLabel}</span>
            )
          )}
          {funnel && (
            <button
              type="button"
              onClick={funnel.onToggle}
              aria-expanded={funnel.expanded}
              aria-controls={funnel.controlsId}
              aria-label={`${funnel.expanded ? "Hide" : "Show"} full funnel`}
              className={inlineControl}
            >
              <ChevronDown
                className={cn("h-3 w-3 transition-transform motion-reduce:transition-none", funnel.expanded && "rotate-180")}
                aria-hidden
              />
            </button>
          )}
        </span>
      )}
    </div>
  )
}

/** Every funnel stage for a live run, shown on request under the metric row. */
export function RunCardFunnel({ id, stages }: { id: string; stages: NonNullable<LiveRun["funnelStages"]> }) {
  return (
    <ul id={id} className="flex flex-wrap gap-x-2.5 gap-y-0.5 text-2xs">
      {stages.map((stage) => (
        <li key={stage.key} className="flex items-baseline gap-1">
          <span className={cn("num font-semibold", stage.colorClass)}>{fmtNum(stage.count)}</span>
          <span className="text-muted">{stage.label}</span>
        </li>
      ))}
    </ul>
  )
}
