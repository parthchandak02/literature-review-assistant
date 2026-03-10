import { Suspense, lazy, useEffect, useMemo, useState } from "react"
import { Activity, BarChart3, BookOpen, ChevronRight, Database, FileText, FileCode2, ClipboardCheck } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { Spinner } from "@/components/ui/feedback"
import { ActivityView } from "@/views/ActivityView"
import type { ReviewEvent } from "@/lib/api"
import { fetchRunEvents } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import { computeFunnelStages } from "@/lib/funnelStages"

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
const ReferencesView = lazy(() =>
  import("@/views/ReferencesView").then((m) => ({ default: m.ReferencesView })),
)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RunTab = "activity" | "results" | "database" | "cost" | "config" | "review-screening" | "references"

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

/** Tab order follows the review workflow: Config (YAML) -> Activity -> Data -> Cost -> Results -> References */
const TAB_ITEMS: { id: RunTab; label: string; icon: React.ElementType; step: number }[] = [
  { id: "config", label: "Config", icon: FileCode2, step: 1 },
  { id: "activity", label: "Activity", icon: Activity, step: 2 },
  { id: "database", label: "Data", icon: Database, step: 3 },
  { id: "cost", label: "Cost", icon: BarChart3, step: 4 },
  { id: "results", label: "Results", icon: FileText, step: 5 },
  { id: "references", label: "References", icon: BookOpen, step: 6 },
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
}: RunViewProps) {
  const [wfIdCopied, setWfIdCopied] = useState(false)
  // For historical runs, events prop is [] (only live runs get the SSE stream).
  // Fetch stored events once so the funnel can be computed for completed runs too.
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [historicalEventsLoading, setHistoricalEventsLoading] = useState(false)
  const isHistorical = events.length === 0

  useEffect(() => {
    if (!isHistorical) {
      // Clearing stale historical events when a live run starts is the intended
      // side effect -- the linter flags it but this is the correct React pattern
      // for resetting derived state when a condition changes.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHistoricalEvents([])
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setHistoricalEventsLoading(false)
      return
    }
    let cancelled = false
    setHistoricalEventsLoading(true)
    void fetchRunEvents(run.runId)
      .then((evts) => {
        if (!cancelled) setHistoricalEvents(evts)
      })
      .finally(() => {
        if (!cancelled) setHistoricalEventsLoading(false)
      })
    return () => { cancelled = true }
  }, [run.runId, isHistorical])

  // Use live SSE events when available; fall back to replayed historical events.
  const effectiveEvents = isHistorical ? historicalEvents : events

  const isDone = run.isDone || status === "done"
  const isRunning = status === "streaming" || status === "connecting"
  // A live run is awaiting human review when a phase_start("human_review_checkpoint")
  // event exists but no matching phase_done has been emitted yet.
  const isAwaitingReview =
    run.historicalStatus === "awaiting_review" ||
    status === "awaiting_review" ||
    (isRunning &&
      events.some((e) => e.type === "phase_start" && e.phase === "human_review_checkpoint") &&
      !events.some((e) => e.type === "phase_done" && e.phase === "human_review_checkpoint"))

  // historicalStatus is the authoritative backend status for completed/cancelled/failed runs.
  // Check it before isDone, because isDone is true for ALL terminal states (including
  // cancelled and failed) -- using isDone alone conflates cancellation with success.
  const isCancelled =
    ["cancelled", "interrupted"].includes((run.historicalStatus ?? "").toLowerCase()) ||
    status === "cancelled"
  const isFailed =
    ["failed", "error"].includes((run.historicalStatus ?? "").toLowerCase()) ||
    status === "error"

  // Derive stats for the info strip.
  // For live runs: use SSE-derived costStats + event counts.
  // For historical runs: fall back to data baked into SelectedRun from HistoryEntry.

  // Compute the full pipeline funnel stages from events (both live and replayed historical).
  const funnelStages = useMemo(() => computeFunnelStages(effectiveEvents), [effectiveEvents])

  // Fallback simple counts used when there are no events at all (e.g. history entry
  // viewed before the event stream has loaded or for very old runs without events).
  const fallbackFound = run.papersFound ?? null
  const fallbackIncluded = run.papersIncluded ?? null

  // Accumulate DB-sourced historical cost (all phases, all prior sessions) with the
  // current live-session SSE cost (writing phase only). This ensures the header never
  // drops below what is already recorded in cost_records, even during a resume:
  //   fresh run:     historicalCost=null  + SSE cost  = running live total
  //   completed run: historicalCost=$0.34 + SSE=0     = full DB total
  //   live resume:   historicalCost=$0.30 + SSE=$0.016 = accumulated approx total
  const displayCost = (() => {
    const total = (run.historicalCost ?? 0) + costStats.total_cost
    return total > 0 ? total : null
  })()

  const statusLabel =
    isAwaitingReview && !isDone
      ? "Awaiting Review"
      : isRunning
        ? "Running"
        : isCancelled
          ? "Cancelled"
          : isFailed
            ? "Failed"
            : status === "done" || isDone
              ? "Completed"
              : "Ready"

  const statusClass =
    isAwaitingReview && !isDone
      ? "text-amber-400"
      : isRunning
        ? "text-violet-400"
        : isCancelled
          ? "text-amber-400"
          : isFailed
            ? "text-red-400"
            : status === "done" || isDone
              ? "text-emerald-400"
              : "text-zinc-500"

  return (
    <div className="flex flex-col gap-0 h-full">
      {/* Run info strip */}
      <div className="flex items-center gap-2 px-6 py-2 border-b border-zinc-800/60 bg-zinc-900/30 shrink-0 overflow-x-auto scrollbar-none text-meta" style={{ touchAction: 'pan-x' }}>
        <span className={cn("font-semibold shrink-0", statusClass)}>
          {statusLabel}
        </span>
        {run.createdAt && (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>{formatRunDate(run.createdAt)}</InfoPill>
          </>
        )}
        {/* Paper funnel: shows each filtering stage as count -> count -> ... */}
        {funnelStages.length > 0 ? (
          <>
            <InfoPill dim>|</InfoPill>
            <InfoPill>
              <span className="flex items-baseline gap-1 flex-wrap">
                {funnelStages.map((stage, i) => (
                  <span key={stage.key} className="flex items-baseline gap-1 shrink-0">
                    {i > 0 && (
                      <span className="text-zinc-600 select-none mx-0.5">&gt;</span>
                    )}
                    <span className={cn("font-semibold", stage.colorClass)}>
                      {stage.count.toLocaleString()}
                    </span>
                    <span className="text-zinc-500">{stage.label}</span>
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
                  <span className="text-blue-400">{fallbackFound.toLocaleString()}</span>
                  <span> found</span>
                </InfoPill>
              </>
            )}
            {fallbackIncluded != null && fallbackIncluded > 0 && (
              <>
                <InfoPill dim>|</InfoPill>
                <InfoPill>
                  <span className="text-emerald-400">{fallbackIncluded.toLocaleString()}</span>
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
                onClick={() => onTabChange("cost")}
                className="text-amber-400 hover:text-amber-300 transition-colors"
              >
                ${displayCost.toFixed(3)}
              </button>
            </InfoPill>
          </>
        )}
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
                className="hover:text-zinc-400 transition-colors cursor-pointer"
                title="Copy workflow ID"
              >
                {wfIdCopied ? "Copied!" : formatWorkflowId(run.workflowId ?? run.runId)}
              </button>
            </InfoPill>
          </>
        )}
      </div>

      {/* Tab bar -- workflow order: Config -> Activity -> Data -> Cost -> Results */}
      {/* touch-action: pan-x locks iOS touch to horizontal-only scrolling on this bar */}
      <div className="flex items-center gap-0 px-3 pt-4 pb-0 border-b border-zinc-800 shrink-0 overflow-x-auto scrollbar-none" style={{ touchAction: 'pan-x' }}>
        {TAB_ITEMS.map((tab, idx) => (
          <div key={tab.id} className="flex items-center shrink-0">
            {idx > 0 && (
              <ChevronRight
                className={cn(
                  "h-3.5 w-3.5 mx-0.5 shrink-0",
                  activeTab === tab.id ? "text-violet-500" : "text-zinc-600",
                )}
                aria-hidden
              />
            )}
            <button
              onClick={() => onTabChange(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap shrink-0",
                activeTab === tab.id
                  ? "border-violet-500 text-white"
                  : "border-transparent text-zinc-500 hover:text-zinc-300",
              )}
              title={`Step ${tab.step}: ${tab.label}`}
            >
              <span className="text-[10px] font-mono tabular-nums text-zinc-600 w-3.5 shrink-0">
                {tab.step}
              </span>
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          </div>
        ))}
        {/* Review Screening: conditional HITL step, shown when awaiting human approval */}
        {isAwaitingReview && (
          <>
            <span className="text-zinc-600 mx-2 shrink-0" aria-hidden>|</span>
            <button
              onClick={() => onTabChange("review-screening")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap shrink-0",
                activeTab === "review-screening"
                  ? "border-amber-500 text-amber-400"
                  : "border-amber-700 text-amber-600 hover:text-amber-400",
              )}
            >
              <ClipboardCheck className="h-3.5 w-3.5" />
              Review Screening
            </button>
          </>
        )}
      </div>

      {/* Tab content -- pb accounts for iOS/Chrome bottom safe area (home bar, bottom nav) */}
      <div className="flex-1 overflow-y-auto overscroll-none p-6" style={{ paddingBottom: 'max(1.5rem, env(safe-area-inset-bottom))' }}>
        <Suspense fallback={<ViewLoader />}>
          {activeTab === "activity" && (
            <ActivityView
              events={events}
              prefetchedHistoricalEvents={isHistorical ? historicalEvents : null}
              historicalEventsLoading={isHistorical ? historicalEventsLoading : false}
              status={status}
              runId={run.runId}
              workflowId={run.workflowId}
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
              isLive={isLive}
            />
          )}

          {activeTab === "config" && (
            <ConfigView
              workflowId={run.workflowId ?? run.runId}
              topic={run.topic}
              createdAt={run.createdAt}
            />
          )}

          {activeTab === "review-screening" && (
            <ScreeningReviewView runId={run.runId} />
          )}

          {activeTab === "references" && (
            <ReferencesView
              runId={run.runId}
              workflowId={run.workflowId}
              isDone={isDone}
            />
          )}
        </Suspense>
      </div>
    </div>
  )
}
