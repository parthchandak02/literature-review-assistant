import { Suspense, lazy, useEffect, useRef, useState } from "react"
import { AlertTriangle, Check, Copy } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { LiveStreamStatus } from "@/components/run-status"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { useEdgeFade } from "@/hooks/useEdgeFade"
import { Button } from "@/components/ui/button"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { NEEDS_REVISION_EXPLANATION } from "@/lib/constants"
import { AUDIT_FINDINGS_ANCHOR } from "@/lib/resultsCategories"
import type { RunChromeVM } from "@/hooks/useRunChrome"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"
import { RunFunnelPopover } from "./RunFunnelPopover"
import { orderRunTabs } from "./runRouting"
import { screeningTabFor } from "./screeningTab"
import { formatChromeCost, formatOutcome } from "./runChromeFormat"

const SubmissionPackageButton = lazy(() =>
  import("@/components/results/SubmissionPackageButton").then((m) => ({ default: m.SubmissionPackageButton })),
)

function Divider() {
  return <span aria-hidden className="h-3 w-px shrink-0 bg-border max-sm:hidden" />
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
      <span className="num text-2xs" title={id}>
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
  const metaRef = useRef<HTMLDivElement | null>(null)
  const metaFadeStyle = useEdgeFade(metaRef)
  const canDownloadPackage = isDone && !isRunning && Boolean(run.runId) && run.runId !== "draft"
  const outcome = formatOutcome(outcomeIncluded, outcomeRecords)
  const showFunnel = displayFunnelStages.length > 1
  const showCost = displayCost != null && displayCost > 0
  const workflowId = run.workflowId ?? run.runId
  const tabs = orderRunTabs<RunChromeTabItem & { accent?: "violet" | "amber" }>(
    tabItems,
    screeningTabFor({ isAwaitingReview, hasScreeningDecisions: chrome.hasScreeningDecisions, activeTab }),
  )

  return (
    <ViewToolbar
      bordered
      className="!h-auto shrink-0 flex-col items-stretch gap-0 !px-0 py-0"
      style={{ touchAction: "pan-x" }}
    >
      <div className="@container flex items-center justify-between gap-3 px-6 pt-2 pb-1 font-sans text-xs tabular-nums text-muted w-full min-w-0">
        <div
          ref={metaRef}
          style={metaFadeStyle}
          className="flex items-center gap-2.5 min-w-0 overflow-x-auto overflow-y-hidden scrollbar-none pointer-coarse:pe-1.5 max-sm:flex-wrap max-sm:gap-x-3 max-sm:gap-y-1 max-sm:overflow-visible"
          data-testid="run-meta-strip"
        >
          <span
            className={cn("font-sans text-xs font-semibold shrink-0", statusClass)}
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
                {outcome.split(/(\d[\d,]*)/).map((part, i) =>
                  i % 2 === 1 ? (
                    <span key={i} className="num font-semibold">
                      {part}
                    </span>
                  ) : (
                    part
                  ),
                )}
              </span>
            </>
          )}
          {(showFunnel || showCost) && (
            <span className="contents max-sm:flex max-sm:basis-full max-sm:items-center max-sm:gap-3">
              {showFunnel && (
                <>
                  <Divider />
                  <span className="flex shrink-0">
                    <RunFunnelPopover stages={displayFunnelStages} />
                  </span>
                </>
              )}
              {showCost && (
                <>
                  <Divider />
                  <button
                    type="button"
                    onClick={() => onTabChange("cost")}
                    className="touch-hit num inline-flex shrink-0 items-center rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring pointer-coarse:min-h-6"
                    title="Open cost breakdown"
                  >
                    {formatChromeCost(displayCost)}
                  </button>
                </>
              )}
            </span>
          )}
          {run.createdAt && (
            <span className="contents max-sm:hidden @max-3xl:hidden">
              <Divider />
              <span className="shrink-0 text-muted">{formatRunDate(run.createdAt)}</span>
            </span>
          )}
          {workflowId && (
            <span className="contents max-sm:hidden @max-2xl:hidden">
              <Divider />
              <CopyWorkflowId id={workflowId} />
            </span>
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
          className="min-w-0 border-b-0 pb-px max-lg:[&_[role=tab]>svg]:hidden"
        />
        {canDownloadPackage && (
          <div className="hidden sm:flex items-center shrink-0 py-1">
            <Suspense fallback={null}>
              <SubmissionPackageButton
                runId={run.runId}
                className="max-lg:w-7 max-lg:gap-0 max-lg:px-0 max-lg:text-[length:0]"
              />
            </Suspense>
          </div>
        )}
      </div>
    </ViewToolbar>
  )
}
