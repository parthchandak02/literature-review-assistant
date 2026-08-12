import { Suspense, lazy } from "react"
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
import { ActivityView } from "@/views/ActivityView"
import type { ReviewEvent } from "@/lib/api"
import { useHistoricalEvents } from "@/hooks/useHistoricalEvents"
import type { CostStats } from "@/hooks/useCostStats"
import { useRunChrome } from "@/hooks/useRunChrome"
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

/** Tab order follows the review workflow: Config (YAML) -> Activity -> Data -> Cost -> Results */
const TAB_ITEMS: { id: RunTab; label: string; icon: React.ElementType }[] = [
  { id: "config", label: "Config", icon: FileCode2 },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "database", label: "Data", icon: Database },
  { id: "cost", label: "Cost", icon: BarChart3 },
  { id: "results", label: "Results", icon: FileText },
]

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
  onPrepareProspero?: (yaml: string) => void
  onStartResearchAfterProspero?: (registration: ProsperoRegistration) => void | Promise<void>
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
  onPrepareProspero,
  onStartResearchAfterProspero,
  onApproveScreeningAndResume,
}: RunViewProps) {
  const isHistorical = !isViewingLiveRun
  const historicalQuery = useHistoricalEvents(run.workflowId, run.runId, {
    enabled: isHistorical,
    attachPending: run.attachPending,
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
  } = chrome

  return (
    <div className="flex flex-col gap-0 h-full">
      {run.attachPending && (
        <div
          className="shrink-0 border-b border-intent-warning/40 bg-intent-warning-subtle px-6 py-2 text-sm text-intent-warning"
          role="status"
        >
          Connecting to run session… Event replay uses workflow SQLite until attach completes.
        </div>
      )}
      <RunChrome
        run={run}
        chrome={chrome}
        tabItems={TAB_ITEMS}
        activeTab={activeTab}
        onTabChange={onTabChange}
        isViewingLiveRun={isViewingLiveRun}
        status={status}
      />

      {/* Tab content -- pb accounts for iOS/Chrome bottom safe area (home bar, bottom nav) */}
      <div className="flex-1 overflow-y-auto overscroll-none p-6" style={{ paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))' }}>
        <ViewBoundary label={activeTab} resetKey={activeTab}>
          <Suspense fallback={<ViewLoader />}>
          {activeTab === "activity" && (
            <ActivityView
              events={events}
              prefetchedHistoricalEvents={isHistorical ? historicalEvents : null}
              historicalEventsLoading={isHistorical ? historicalEventsLoading : false}
              allowHistoricalFallback={isHistorical}
              attachPending={run.attachPending}
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
              onPrepareProspero={onPrepareProspero}
              onStartResearchAfterProspero={onStartResearchAfterProspero}
            />
          )}

          {activeTab === "review-screening" && (
            <ScreeningReviewView
              runId={run.runId}
              onApproveAndResume={onApproveScreeningAndResume}
            />
          )}
          </Suspense>
        </ViewBoundary>
      </div>
    </div>
  )
}
