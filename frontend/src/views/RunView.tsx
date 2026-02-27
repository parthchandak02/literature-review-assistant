import { Suspense, lazy, useState } from "react"
import { Activity, BarChart3, Database, FileText, ClipboardCheck, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { Spinner } from "@/components/ui/feedback"
import { ActivityView } from "@/views/ActivityView"
import { livingRefresh } from "@/lib/api"
import type { ReviewEvent } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"

const CostView = lazy(() => import("@/views/CostView").then((m) => ({ default: m.CostView })))
const DatabaseView = lazy(() =>
  import("@/views/DatabaseView").then((m) => ({ default: m.DatabaseView })),
)
const ResultsView = lazy(() =>
  import("@/views/ResultsView").then((m) => ({ default: m.ResultsView })),
)
const ScreeningReviewView = lazy(() =>
  import("@/views/ScreeningReviewView").then((m) => ({ default: m.ScreeningReviewView })),
)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RunTab = "activity" | "results" | "database" | "cost" | "review-screening"

/** A run that is currently being viewed (live or historical). */
export interface SelectedRun {
  /** Backend run_id for /api/db/{runId}/... and /api/run/{runId}/... calls. */
  runId: string
  /** Stable workflow UUID -- available after run completes or for historical runs. */
  workflowId: string | null
  topic: string
  dbPath: string | null
  isDone: boolean
  startedAt: Date | null
  /** Populated from HistoryEntry for historical runs; null for live runs. */
  createdAt?: string | null
  papersFound?: number | null
  papersIncluded?: number | null
  historicalCost?: number | null
  /** Raw backend status string for historical runs (e.g. "running", "failed", "completed"). */
  historicalStatus?: string | null
}

const TAB_ITEMS: { id: RunTab; label: string; icon: React.ElementType }[] = [
  { id: "activity", label: "Activity", icon: Activity },
  { id: "results", label: "Results", icon: FileText },
  { id: "database", label: "Data", icon: Database },
  { id: "cost", label: "Cost", icon: BarChart3 },
]

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <Spinner size="md" className="text-violet-500" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Run info strip helpers
// ---------------------------------------------------------------------------

interface InfoPillProps {
  children: React.ReactNode
  dim?: boolean
}

function InfoPill({ children, dim }: InfoPillProps) {
  return (
    <span className={cn("shrink-0", dim ? "text-zinc-600" : "text-zinc-400")}>
      {children}
    </span>
  )
}

// ---------------------------------------------------------------------------
// RunView
// ---------------------------------------------------------------------------

interface RunViewProps {
  run: SelectedRun
  /** Live SSE events -- empty when viewing a historical run. */
  events: ReviewEvent[]
  /** SSE connection status. */
  status: string
  costStats: CostStats
  activeTab: RunTab
  onTabChange: (tab: RunTab) => void
  onCancel: () => void
  /** Artifacts from run_summary.json for historical completed runs. */
  historyOutputs: Record<string, string>
  /** Outputs from the live "done" SSE event. */
  liveOutputs: Record<string, unknown>
  /** True once backend emits db_ready (or the run is historical). */
  dbUnlocked: boolean
  /** True while the run is still streaming (for DatabaseView auto-refresh). */
  isLive: boolean
  /** Called when the user requests a living-review refresh run. */
  onLivingRefresh?: (runId: string) => void
}

export function RunView({
  run,
  events,
  status,
  costStats,
  activeTab,
  onTabChange,
  onCancel,
  historyOutputs,
  liveOutputs,
  dbUnlocked,
  isLive,
  onLivingRefresh,
}: RunViewProps) {
  const [refreshing, setRefreshing] = useState(false)
  const isDone = run.isDone || status === "done"
  const isRunning = status === "streaming" || status === "connecting"

  async function handleLivingRefresh() {
    if (refreshing || !onLivingRefresh) return
    setRefreshing(true)
    try {
      const data = await livingRefresh(run.runId)
      onLivingRefresh(data.run_id)
    } catch (e) {
      console.error("Living refresh error:", e)
    } finally {
      setRefreshing(false)
    }
  }

  // Derive stats for the info strip.
  // For live runs: use SSE-derived costStats + event counts.
  // For historical runs: fall back to data baked into SelectedRun from HistoryEntry.
  const livePapersFound = events
    .filter((e) => e.type === "connector_result" && e.status === "success")
    .reduce((acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0), 0)

  const liveIncluded = events.filter(
    (e) => e.type === "screening_decision" && e.decision === "include",
  ).length

  const displayPapersFound =
    livePapersFound > 0 ? livePapersFound : (run.papersFound ?? null)
  const displayIncluded =
    liveIncluded > 0 ? liveIncluded : (run.papersIncluded ?? null)
  const displayCost =
    costStats.total_cost > 0 ? costStats.total_cost : (run.historicalCost ?? null)

  const statusLabel =
    isRunning
      ? "Running"
      : status === "done" || isDone
        ? "Completed"
        : status === "error"
          ? "Failed"
          : status === "cancelled"
            ? "Cancelled"
            : "Ready"

  const statusClass =
    isRunning
      ? "text-violet-400"
      : status === "done" || isDone
        ? "text-emerald-400"
        : status === "error"
          ? "text-red-400"
          : status === "cancelled"
            ? "text-amber-400"
            : "text-zinc-500"

  return (
    <div className="flex flex-col gap-0 h-full">
      {/* Run info strip */}
      <div className="flex items-center gap-2 px-6 py-2 border-b border-zinc-800/60 bg-zinc-900/30 shrink-0 overflow-x-auto scrollbar-none text-[11px] font-mono">
        <span className={cn("font-semibold shrink-0", statusClass)}>
          {statusLabel}
        </span>
        {run.createdAt && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>{formatRunDate(run.createdAt)}</InfoPill>
          </>
        )}
        {displayPapersFound != null && displayPapersFound > 0 && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>{displayPapersFound.toLocaleString()} found</InfoPill>
          </>
        )}
        {displayIncluded != null && displayIncluded > 0 && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>{displayIncluded.toLocaleString()} included</InfoPill>
          </>
        )}
        {displayCost != null && displayCost > 0 && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>
              <button
                onClick={() => onTabChange("cost")}
                className="hover:text-violet-400 transition-colors"
              >
                ${displayCost.toFixed(3)}
              </button>
            </InfoPill>
          </>
        )}
        {(run.workflowId ?? run.runId) && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill dim>{formatWorkflowId(run.workflowId ?? run.runId)}</InfoPill>
          </>
        )}
        {/* Living review refresh button -- only shown for completed runs */}
        {isDone && onLivingRefresh && (
          <>
            <InfoPill dim>|</InfoPill>
            <button
              onClick={() => void handleLivingRefresh()}
              disabled={refreshing}
              className="inline-flex items-center gap-1 text-violet-500 hover:text-violet-300 transition-colors disabled:opacity-50"
              title="Launch an incremental living-review run to pick up new papers"
            >
              <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
              <span className="shrink-0">{refreshing ? "Starting..." : "Refresh Search"}</span>
            </button>
          </>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 px-6 pt-4 pb-0 border-b border-zinc-800 shrink-0">
        {TAB_ITEMS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === tab.id
                ? "border-violet-500 text-white"
                : "border-transparent text-zinc-500 hover:text-zinc-300",
            )}
          >
            <tab.icon className="h-3.5 w-3.5" />
            {tab.label}
          </button>
        ))}
        {/* Show "Review Screening" tab when run is awaiting human review */}
        {(run.historicalStatus === "awaiting_review" || status === "awaiting_review") && (
          <button
            onClick={() => onTabChange("review-screening")}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === "review-screening"
                ? "border-amber-500 text-amber-400"
                : "border-amber-700 text-amber-600 hover:text-amber-400",
            )}
          >
            <ClipboardCheck className="h-3.5 w-3.5" />
            Review Screening
          </button>
        )}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        <Suspense fallback={<ViewLoader />}>
          {activeTab === "activity" && (
            <ActivityView
              events={events}
              status={status}
              runId={run.runId}
              isDone={isDone}
              onCancel={onCancel}
            />
          )}

          {activeTab === "results" && (
            <ResultsView
              outputs={liveOutputs}
              isDone={isDone}
              historyOutputs={historyOutputs}
              exportRunId={isDone ? run.runId : null}
            />
          )}

          {activeTab === "database" && (
            <DatabaseView
              runId={run.runId}
              isDone={isDone}
              dbAvailable={dbUnlocked}
              isLive={isLive}
            />
          )}

          {activeTab === "cost" && (
            <CostView
              costStats={costStats}
              dbRunId={run.runId}
            />
          )}

          {activeTab === "review-screening" && (
            <ScreeningReviewView runId={run.runId} />
          )}
        </Suspense>
      </div>
    </div>
  )
}
