import { useEffect, useRef, useState } from "react"
import { AlertTriangle, Check, ClipboardCheck, Copy } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { LiveStreamStatus } from "@/components/run-status"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { Button } from "@/components/ui/button"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { SubmissionPackageButton } from "@/components/results/SubmissionPackageButton"
import { NEEDS_REVISION_EXPLANATION } from "@/lib/constants"
import { AUDIT_FINDINGS_ANCHOR } from "@/lib/resultsCategories"
import type { RunChromeVM } from "@/hooks/useRunChrome"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"
import { RunFunnelPopover } from "./RunFunnelPopover"
import { orderRunTabs } from "./runRouting"
import { formatChromeCost, formatOutcome } from "./runChromeFormat"

function Divider() {
  return <span aria-hidden className="h-3 w-px shrink-0 bg-border" />
}

export interface RunChromeTabItem {
  id: RunTab
  label: string
  icon: React.ElementType
}

const REVIEW_SCREENING_TAB = {
  id: "review-screening" as RunTab,
  label: "Review Screening",
  icon: ClipboardCheck,
  accent: "amber" as const,
}

export interface RunChromeProps {
  run: SelectedRun
  chrome: RunChromeVM
  tabItems: RunChromeTabItem[]
  activeTab: RunTab
  onTabChange: (tab: RunTab) => void
  isViewingLiveRun: boolean
  status: string
  subStatus?: string | null
}

function CopyWorkflowId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(id)
      setCopied(true)
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("Couldn't copy the workflow ID")
    }
  }

  return (
    <span className="inline-flex items-center gap-0.5 shrink-0 text-muted">
      <span className="font-mono text-2xs" title={id}>
        {formatWorkflowId(id)}
      </span>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        onClick={() => void handleCopy()}
        aria-label="Copy workflow ID"
        title="Copy workflow ID"
      >
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      </Button>
      <span className="sr-only" aria-live="polite">
        {copied ? "Copied" : ""}
      </span>
    </span>
  )
}

export function RunChrome({
  run,
  chrome,
  tabItems,
  activeTab,
  onTabChange,
  isViewingLiveRun,
  status,
  subStatus,
}: RunChromeProps) {
  const {
    statusLabel,
    statusClassName: statusClass,
    displayFunnelStages,
    outcomeIncluded,
    outcomeRecords,
    displayCost,
    isRunning,
    isDone,
    isAwaitingReview,
    isNeedsRevision,
  } = chrome
  const canDownloadPackage = isDone && !isRunning && Boolean(run.runId) && run.runId !== "draft"
  const outcome = formatOutcome(outcomeIncluded, outcomeRecords)
  const workflowId = run.workflowId ?? run.runId
  const tabs = orderRunTabs<RunChromeTabItem & { accent?: "violet" | "amber" }>(
    tabItems,
    isAwaitingReview ? REVIEW_SCREENING_TAB : null,
  )

  return (
    <ViewToolbar
      bordered
      className="!h-auto shrink-0 flex-col items-stretch gap-0 !px-0 py-0"
      style={{ touchAction: "pan-x" }}
    >
      <div className="flex items-center justify-between gap-3 px-6 pt-2 pb-1 text-meta w-full min-w-0">
        <div className="flex items-center gap-2.5 min-w-0 overflow-x-auto scrollbar-none">
          <span
            className={cn("font-semibold shrink-0", statusClass)}
            aria-live="polite"
            aria-atomic="true"
            title={isNeedsRevision ? NEEDS_REVISION_EXPLANATION : undefined}
          >
            {statusLabel}
          </span>
          {subStatus && (
            <span className="shrink-0 tabular-nums text-muted-foreground" data-testid="run-sub-status">
              {subStatus}
            </span>
          )}
          {isNeedsRevision && (
            <button
              type="button"
              onClick={() => {
                window.location.hash = AUDIT_FINDINGS_ANCHOR
                onTabChange("results")
              }}
              className="inline-flex items-center gap-1 shrink-0 text-intent-warning hover:underline"
              title={NEEDS_REVISION_EXPLANATION}
            >
              <AlertTriangle className="h-3 w-3" aria-hidden />
              Review audit findings
            </button>
          )}
          {outcome && (
            <>
              <Divider />
              <span className="shrink-0 text-foreground" data-testid="run-outcome">
                {outcome}
              </span>
            </>
          )}
          {displayCost != null && displayCost > 0 && (
            <>
              <Divider />
              <button
                type="button"
                onClick={() => onTabChange("cost")}
                className="shrink-0 tabular-nums text-muted-foreground hover:text-foreground transition-colors"
                title="Open cost breakdown"
              >
                {formatChromeCost(displayCost)}
              </button>
            </>
          )}
          {displayFunnelStages.length > 1 && (
            <>
              <Divider />
              <RunFunnelPopover stages={displayFunnelStages} />
            </>
          )}
          {run.createdAt && (
            <>
              <Divider />
              <span className="shrink-0 text-muted">{formatRunDate(run.createdAt)}</span>
            </>
          )}
          {workflowId && (
            <>
              <Divider />
              <CopyWorkflowId id={workflowId} />
            </>
          )}
        </div>

        {isViewingLiveRun && isRunning && (
          <div className="flex items-center gap-2 shrink-0">
            <LiveStreamStatus mode={status === "connecting" ? "connecting" : "streaming"} />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 px-6 w-full min-w-0">
        <GlassTabs
          items={tabs.map((tab) => ({ id: tab.id, label: tab.label, icon: tab.icon, accent: tab.accent }))}
          activeTab={activeTab}
          onTabChange={onTabChange}
          variant="underline"
          className="min-w-0 border-b-0 pb-px"
        />
        {canDownloadPackage && (
          <div className="hidden sm:flex items-center shrink-0 py-1">
            <SubmissionPackageButton runId={run.runId} />
          </div>
        )}
      </div>
    </ViewToolbar>
  )
}
