import { useState } from "react"
import { ClipboardCheck } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { LiveStreamStatus } from "@/components/run-status"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import type { RunChromeVM } from "@/hooks/useRunChrome"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"

interface InfoPillProps {
  children: React.ReactNode
  dim?: boolean
}

function InfoPill({ children, dim }: InfoPillProps) {
  return <span className={cn("shrink-0", dim && "text-muted")}>{children}</span>
}

export interface RunChromeTabItem {
  id: RunTab
  label: string
  icon: React.ElementType
}

export interface RunChromeProps {
  run: SelectedRun
  chrome: RunChromeVM
  tabItems: RunChromeTabItem[]
  activeTab: RunTab
  onTabChange: (tab: RunTab) => void
  isViewingLiveRun: boolean
  status: string
}

export function RunChrome({
  run,
  chrome,
  tabItems,
  activeTab,
  onTabChange,
  isViewingLiveRun,
  status,
}: RunChromeProps) {
  const [wfIdCopied, setWfIdCopied] = useState(false)
  const {
    statusLabel,
    statusClassName: statusClass,
    displayFunnelStages,
    fallbackFound,
    fallbackIncluded,
    displayCost,
    isRunning,
    isAwaitingReview,
  } = chrome

  return (
    <ViewToolbar
      bordered
      className="!h-auto shrink-0 flex-col items-stretch gap-0 !px-0 py-0"
      style={{ touchAction: "pan-x" }}
    >
      <div className="flex items-center justify-between gap-3 px-6 py-2 text-meta w-full min-w-0">
        <div className="flex items-center gap-2 min-w-0 overflow-x-auto scrollbar-none">
          <span className={cn("font-semibold shrink-0", statusClass)}>
            {statusLabel}
          </span>
          {(run.workflowId ?? run.runId) && (
            <>
              <InfoPill dim>|</InfoPill>
              <InfoPill dim>
                <button
                  type="button"
                  onClick={async () => {
                    const id = run.workflowId ?? run.runId
                    if (id) {
                      await navigator.clipboard.writeText(id)
                      setWfIdCopied(true)
                      setTimeout(() => setWfIdCopied(false), 1500)
                    }
                  }}
                  className="hover:text-foreground transition-colors cursor-pointer"
                  title="Copy workflow ID"
                >
                  {wfIdCopied ? "Copied!" : formatWorkflowId(run.workflowId ?? run.runId)}
                </button>
              </InfoPill>
            </>
          )}
          {run.createdAt && (
            <>
              <InfoPill dim>|</InfoPill>
              <InfoPill>{formatRunDate(run.createdAt)}</InfoPill>
            </>
          )}
          {displayFunnelStages.length > 0 ? (
            <>
              <InfoPill dim>|</InfoPill>
              <InfoPill>
                <span className="flex items-baseline gap-1 flex-wrap">
                  {displayFunnelStages.map((stage, i) => (
                    <span key={stage.key} className="flex items-baseline gap-1 shrink-0">
                      {i > 0 && (
                        <span className="text-muted select-none mx-0.5">&gt;</span>
                      )}
                      <span className={cn("font-semibold", stage.colorClass)}>
                        {stage.count.toLocaleString()}
                      </span>
                      <span className="text-muted">{stage.label}</span>
                    </span>
                  ))}
                </span>
              </InfoPill>
            </>
          ) : (
            <>
              {fallbackFound != null && fallbackFound > 0 && (
                <>
                  <InfoPill dim>|</InfoPill>
                  <InfoPill>
                    <span className="text-intent-info">{fallbackFound.toLocaleString()}</span>
                    <span> found</span>
                  </InfoPill>
                </>
              )}
              {fallbackIncluded != null && fallbackIncluded > 0 && (
                <>
                  <InfoPill dim>|</InfoPill>
                  <InfoPill>
                    <span className="text-intent-success">{fallbackIncluded.toLocaleString()}</span>
                    <span> included</span>
                  </InfoPill>
                </>
              )}
            </>
          )}
          {displayCost != null && displayCost > 0 && (
            <>
              <InfoPill dim>|</InfoPill>
              <InfoPill>
                <button
                  type="button"
                  onClick={() => onTabChange("cost")}
                  className="text-intent-warning hover:text-intent-warning transition-colors"
                >
                  ${displayCost.toFixed(3)}
                </button>
              </InfoPill>
            </>
          )}
        </div>

        {isViewingLiveRun && isRunning && (
          <div className="flex items-center gap-2 shrink-0">
            <LiveStreamStatus mode={status === "connecting" ? "connecting" : "streaming"} />
          </div>
        )}
      </div>

      <div className="px-3 py-2 w-full">
        <GlassTabs
          items={[
            ...tabItems.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon })),
            ...(isAwaitingReview
              ? [{ id: "review-screening" as RunTab, label: "Review Screening", icon: ClipboardCheck, accent: "amber" as const }]
              : []),
          ]}
          activeTab={activeTab}
          onTabChange={onTabChange}
          equalWidth
        />
      </div>
    </ViewToolbar>
  )
}
