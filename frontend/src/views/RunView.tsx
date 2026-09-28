import { useEffect, useMemo, useRef, useState, Suspense, lazy } from "react"
import {
  Activity,
  BarChart3,
  Database,
  FileCode2,
  FileText,
} from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { ViewBoundary } from "@/components/ViewBoundary"
import { RunChrome } from "@/components/run/RunChrome"
import { RunGateBanner } from "@/components/run/RunGateBanner"
import { explicitTabWorkflowId, resolveAutoRouteTab } from "@/components/run/runRouting"
import { ActivityView } from "@/views/ActivityView"
import type { ReviewEvent } from "@/lib/api"
import { useHistoricalEvents } from "@/hooks/useHistoricalEvents"
import type { CostStats } from "@/hooks/useCostStats"
import { useRunChrome } from "@/hooks/useRunChrome"
import { activeSubStatus, buildPhaseStates, formatSubStatus } from "@/lib/activityPhaseState"
import type { DraftConfigContext } from "@/views/ConfigView"
import type { ProsperoRegistration, ScreeningOverride } from "@/lib/api"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"

export type { RunTab, SelectedRun } from "@/context/runSessionTypes"

const CostView = lazy(() => import("@/views/CostView").then((m) => ({ default: m.CostView })))
const DatabaseView = lazy(() =>
  import("@/views/DatabaseView").then((m) => ({ default: m.DatabaseView })),
)
const ResultsView = lazy(() =>
  import("@/views/ResultsView").then((m) => ({ default: m.ResultsView })),
)
const ConfigView = lazy(() =>
  import("@/views/ConfigView").then((m) => ({ default: m.ConfigView })),
)
const ScreeningReviewView = lazy(() =>
  import("@/views/ScreeningReviewView").then((m) => ({ default: m.ScreeningReviewView })),
)

const TAB_ITEMS: { id: RunTab; label: string; icon: React.ElementType }[] = [
  { id: "activity", label: "Activity", icon: Activity },
  { id: "results", label: "Results", icon: FileText },
  { id: "database", label: "Data", icon: Database },
  { id: "config", label: "Config", icon: FileCode2 },
  { id: "cost", label: "Cost", icon: BarChart3 },
]

/** Workflow deep-linked with an explicit tab on page load; auto-routing skips it once. */
let deepLinkedWorkflowId: string | null =
  typeof window !== "undefined" ? explicitTabWorkflowId(window.location.pathname) : null

function gateFailureReasons(outputs: Record<string, unknown>): string[] {
  const raw = outputs.gate_failure_reasons
  return Array.isArray(raw) ? raw.filter((r): r is string => typeof r === "string") : []
}

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <Spinner size="md" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// RunView
// ---------------------------------------------------------------------------

interface RunViewProps {
  run: SelectedRun
  /** Live SSE events -- empty when viewing a historical run. */
  events: ReviewEvent[]
  /** True when selected run is backed by the live SSE stream. */
  isViewingLiveRun: boolean
  /** SSE connection status. */
  status: string
  costStats: CostStats
  activeTab: RunTab
  onTabChange: (tab: RunTab) => void
  /** Artifacts from run_summary.json for historical completed runs. */
  historyOutputs: Record<string, string>
  /** Outputs from the live "done" SSE event. */
  liveOutputs: Record<string, unknown>
  /** True once backend emits db_ready (or the run is historical). */
  dbUnlocked: boolean
  /** True while the run is still streaming (for DatabaseView auto-refresh). */
  isLive: boolean
  /** True when the live SSE stream is connected and authoritative. */
  isSSEConnected?: boolean
  /** Resume from a specific phase (historical runs only). */
  onResumeFromPhase?: (phase: string) => Promise<void>
  /** True when resume controls were opened from the sidebar launcher. */
  resumeModeActive?: boolean
  /** Highlight target used by Results Files category deep-link. */
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
  draftConfig?: DraftConfigContext | null
  onRetryDraftGeneration?: () => void
  onLaunchDraft?: (yaml: string) => void
  prosperoPrepareInProgress?: boolean
  prosperoSubmitting?: boolean
  prosperoRegenerating?: boolean
  onPrepareProspero?: (yaml: string) => void
  onStartResearchAfterProspero?: (registration: ProsperoRegistration) => void | Promise<void>
  onSaveProsperoRegistration?: (registration: ProsperoRegistration) => void | Promise<void>
  onRegenerateProsperoDrafts?: () => void | Promise<void>
  onApproveScreeningAndResume?: (overrides: ScreeningOverride[]) => Promise<void>
}

export function RunView({
  run,
  events,
  isViewingLiveRun,
  status,
  costStats,
  activeTab,
  onTabChange,
  historyOutputs,
  liveOutputs,
  dbUnlocked,
  isLive,
  isSSEConnected = false,
  onResumeFromPhase,
  resumeModeActive = false,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
  draftConfig = null,
  onRetryDraftGeneration,
  onLaunchDraft,
  prosperoPrepareInProgress = false,
  prosperoSubmitting = false,
  prosperoRegenerating = false,
  onPrepareProspero,
  onStartResearchAfterProspero,
  onSaveProsperoRegistration,
  onRegenerateProsperoDrafts,
  onApproveScreeningAndResume,
}: RunViewProps) {
  const isHistorical = !isViewingLiveRun
  const historicalQuery = useHistoricalEvents(run.workflowId, run.runId, {
    enabled: isHistorical,
  })
  const historicalEvents = historicalQuery.data ?? []
  const historicalEventsLoading = historicalQuery.isPending

  // Use live SSE events when available; fall back to replayed historical events.
  const effectiveEvents = isHistorical ? historicalEvents : events

  const chrome = useRunChrome({
    run,
    events,
    effectiveEvents,
    isViewingLiveRun,
    status,
    costStats,
    liveOutputs,
    prosperoPrepareInProgress,
  })

  const {
    isDone,
    isAwaitingProspero,
    isNeedsRevision,
    gate,
  } = chrome

  const [nowTick, setNowTick] = useState(() => Date.now())
  useEffect(() => {
    if (!isViewingLiveRun) return
    const id = setInterval(() => setNowTick(Date.now()), 15000)
    return () => clearInterval(id)
  }, [isViewingLiveRun])
  const subStatus = useMemo(() => {
    if (!isViewingLiveRun || !chrome.isRunning) return null
    const sub = activeSubStatus(buildPhaseStates(events, false), nowTick)
    return sub ? formatSubStatus(sub) : null
  }, [isViewingLiveRun, chrome.isRunning, events, nowTick])

  const runKey = run.workflowId ?? run.runId
  const routedRef = useRef<string | null>(null)
  const suppressedRunRef = useRef<string | null>(null)

  useEffect(() => {
    if (deepLinkedWorkflowId && deepLinkedWorkflowId === run.workflowId) {
      suppressedRunRef.current = runKey
      deepLinkedWorkflowId = null
    }
    if (!gate) return
    const routeKey = `${runKey}:${gate}`
    if (routedRef.current === routeKey) return
    routedRef.current = routeKey
    const target = resolveAutoRouteTab({
      gate,
      activeTab,
      explicitDeepLink: suppressedRunRef.current === runKey,
    })
    if (target) onTabChange(target)
  }, [gate, runKey, run.workflowId, activeTab, onTabChange])

  return (
    <div className="flex flex-col gap-0 h-full">
      <RunChrome
        run={run}
        chrome={chrome}
        tabItems={TAB_ITEMS}
        activeTab={activeTab}
        onTabChange={onTabChange}
        isViewingLiveRun={isViewingLiveRun}
        status={status}
        subStatus={subStatus}
      />
      <RunGateBanner gate={gate} activeTab={activeTab} onTabChange={onTabChange} />

      {/* Tab content -- pb accounts for iOS/Chrome bottom safe area (home bar, bottom nav) */}
      <div
        className="flex-1 overflow-y-auto overscroll-none p-6"
        style={{ paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))' }}
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        <ViewBoundary label={activeTab} resetKey={activeTab}>
          <Suspense fallback={<ViewLoader />}>
          {activeTab === "activity" && (
            <ActivityView
              events={events}
              prefetchedHistoricalEvents={isHistorical ? historicalEvents : null}
              historicalEventsLoading={isHistorical ? historicalEventsLoading : false}
              allowHistoricalFallback={isHistorical}
              status={status}
              runId={run.runId}
              workflowId={run.workflowId}
              historicalStatus={run.historicalStatus}
              onResumeFromPhase={onResumeFromPhase}
              resumeModeActive={resumeModeActive}
            />
          )}

          {activeTab === "results" && (
            <ResultsView
              outputs={liveOutputs}
              isDone={isDone}
              runId={run.runId}
              workflowId={run.workflowId}
              historyOutputs={historyOutputs}
              exportRunId={isDone ? run.runId : null}
              submissionFocusTarget={submissionFocusTarget}
              submissionFocusToken={submissionFocusToken}
              needsRevision={isNeedsRevision}
              gateFailureReasons={gateFailureReasons(liveOutputs)}
              onOpenActivity={() => onTabChange("activity")}
            />
          )}

          {activeTab === "database" && (
            <DatabaseView
              runId={run.runId}
              isDone={isDone}
              dbAvailable={dbUnlocked}
              isLive={isLive}
              isSSEConnected={isSSEConnected}
            />
          )}

          {activeTab === "cost" && (
            <CostView
              costStats={costStats}
              dbRunId={run.runId}
              workflowId={run.workflowId}
              isLive={isLive}
              isSSEConnected={isSSEConnected}
            />
          )}

          {activeTab === "config" && (
            <ConfigView
              workflowId={run.workflowId}
              draftConfig={draftConfig}
              onRetryDraftGeneration={onRetryDraftGeneration}
              onLaunchDraft={onLaunchDraft}
              runId={run.runId}
              isAwaitingProspero={isAwaitingProspero}
              prosperoPrepareInProgress={prosperoPrepareInProgress}
              prosperoSubmitting={prosperoSubmitting}
              prosperoRegenerating={prosperoRegenerating}
              onPrepareProspero={onPrepareProspero}
              onStartResearchAfterProspero={onStartResearchAfterProspero}
              onSaveProsperoRegistration={onSaveProsperoRegistration}
              onRegenerateProsperoDrafts={onRegenerateProsperoDrafts}
            />
          )}

          {activeTab === "review-screening" && (
            <ScreeningReviewView
              key={run.workflowId ?? run.runId}
              runId={run.runId}
              workflowId={run.workflowId}
              onApproveAndResume={onApproveScreeningAndResume}
            />
          )}
          </Suspense>
        </ViewBoundary>
      </div>
    </div>
  )
}
