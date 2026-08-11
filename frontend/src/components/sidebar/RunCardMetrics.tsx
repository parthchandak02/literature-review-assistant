import { useState } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatWorkflowId } from "@/lib/format"
import type { FunnelStage } from "@/lib/funnelStages"

function fmtNum(n: number): string {
  return n.toLocaleString()
}

function resolveSummaryCounts(
  papersFound: number | null | undefined,
  papersIncluded: number | null | undefined,
  funnelStages: FunnelStage[] | undefined,
): { found: number | null; included: number | null } {
  let found = papersFound ?? null
  let included = papersIncluded ?? null

  if (funnelStages != null && funnelStages.length > 0) {
    if (found == null) found = funnelStages[0]?.count ?? null
    const includedStage = funnelStages.find((s) => s.key === "included")
    if (included == null && includedStage != null) included = includedStage.count
  }

  return { found, included }
}

function FunnelStageList({ stages }: { stages: FunnelStage[] }) {
  return (
    <>
      {stages.map((stage) => (
        <span key={stage.key} className="flex items-baseline gap-1 leading-none">
          <span className={cn("font-semibold tabular-nums", stage.colorClass)}>
            {fmtNum(stage.count)}
          </span>
          <span className="text-muted font-normal">{stage.label}</span>
        </span>
      ))}
    </>
  )
}

function SummaryLine({ found, included }: { found: number | null; included: number | null }) {
  if (found != null && included != null) {
    return (
      <span className="flex items-baseline gap-1 leading-none min-w-0">
        <span className="font-semibold tabular-nums text-intent-info">{fmtNum(found)}</span>
        <span className="text-muted font-normal">found</span>
        <span className="text-muted font-normal">→</span>
        <span className="font-semibold tabular-nums text-intent-success">{fmtNum(included)}</span>
        <span className="text-muted font-normal">included</span>
      </span>
    )
  }

  if (found != null) {
    return (
      <span className="flex items-baseline gap-1 leading-none">
        <span className="font-semibold tabular-nums text-intent-info">{fmtNum(found)}</span>
        <span className="text-muted font-normal">found</span>
      </span>
    )
  }

  if (included != null) {
    return (
      <span className="flex items-baseline gap-1 leading-none">
        <span className="font-semibold tabular-nums text-intent-success">{fmtNum(included)}</span>
        <span className="text-muted font-normal">included</span>
      </span>
    )
  }

  return null
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
  const [expanded, setExpanded] = useState(false)
  const hasFunnel = funnelStages != null && funnelStages.length > 0
  const { found, included } = resolveSummaryCounts(papersFound, papersIncluded, funnelStages)
  const hasStats =
    hasFunnel ||
    found != null ||
    included != null ||
    (cost != null && cost > 0)
  const hasWfId = workflowId != null && workflowId.length > 0

  if (!hasStats && !hasWfId) return null

  return (
    <div className="flex justify-between items-start gap-x-2 min-w-0 text-meta w-full">
      <div className="flex flex-col gap-y-0.5 min-w-0">
        {expanded && hasFunnel ? (
          <FunnelStageList stages={funnelStages!} />
        ) : (
          <div className="flex items-center gap-1 min-w-0">
            <SummaryLine found={found} included={included} />
            {hasFunnel && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setExpanded(true)
                }}
                aria-label="Show funnel stages"
                title="Show funnel stages"
                className="shrink-0 flex items-center justify-center h-4 w-4 rounded text-muted hover:text-foreground transition-colors"
              >
                <ChevronDown className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
        {expanded && hasFunnel && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(false)
            }}
            aria-label="Hide funnel stages"
            title="Hide funnel stages"
            className="self-start flex items-center gap-0.5 text-muted hover:text-foreground transition-colors"
          >
            <ChevronDown className="h-3 w-3 rotate-180" />
            <span className="text-[10px] font-medium">Less</span>
          </button>
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
