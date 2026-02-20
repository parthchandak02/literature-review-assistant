import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle,
  Circle,
  Clock,
  DollarSign,
  FileSearch,
  Filter,
  Layers,
  Loader,
  Loader2,
  XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { LogStream } from "@/components/LogStream"
import { FetchError } from "@/components/ui/feedback"
import { fetchRunEvents } from "@/lib/api"
import type { ReviewEvent } from "@/lib/api"
import { useCostStats } from "@/hooks/useCostStats"
import type { CostStats } from "@/hooks/useCostStats"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Phase timeline helpers
// ---------------------------------------------------------------------------

const PHASE_ORDER = [
  "phase_2_search",
  "phase_3_screening",
  "phase_4_extraction_quality",
  "phase_5_synthesis",
  "phase_6_writing",
  "finalize",
]

const PHASE_LABELS: Record<string, string> = {
  phase_2_search: "Search",
  phase_3_screening: "Screening",
  phase_4_extraction_quality: "Extraction & Quality",
  phase_5_synthesis: "Synthesis",
  phase_6_writing: "Writing",
  finalize: "Finalize",
}

type PhaseStatus = "pending" | "running" | "done"

interface PhaseState {
  status: PhaseStatus
  progress?: { current: number; total: number }
  startedTs?: string
  doneTss?: string
}

function buildPhaseStates(events: ReviewEvent[]): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = {
        status: "running",
        startedTs: ev.ts,
      }
    } else if (ev.type === "phase_done") {
      states[ev.phase] = {
        status: "done",
        startedTs: states[ev.phase]?.startedTs,
        doneTss: ev.ts,
        progress:
          ev.total != null && ev.completed != null
            ? { current: ev.completed, total: ev.total }
            : undefined,
      }
    } else if (ev.type === "progress" && states[ev.phase]) {
      states[ev.phase].progress = { current: ev.current, total: ev.total }
    }
  }
  return states
}

/** Format a duration in milliseconds as "Xm Ys" or "Xs". */
function fmtDuration(ms: number): string {
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

/** Derive total elapsed from first/last event timestamp strings. */
function derivedElapsedFromEvents(events: ReviewEvent[]): string {
  if (events.length < 2) return "--"
  const tsList = events
    .map((e) => ("ts" in e && e.ts ? new Date(e.ts).getTime() : NaN))
    .filter((t) => !isNaN(t))
  if (tsList.length < 2) return "--"
  const ms = Math.max(...tsList) - Math.min(...tsList)
  return fmtDuration(ms)
}

const TERMINAL_STATUSES = new Set(["done", "error", "cancelled"])

function useElapsed(startedAt: Date | null, status: string): string {
  const [elapsed, setElapsed] = useState("--")
  const stopped = TERMINAL_STATUSES.has(status)
  useEffect(() => {
    if (!startedAt || stopped) return
    const compute = () => {
      const secs = Math.floor((Date.now() - startedAt.getTime()) / 1000)
      setElapsed(`${Math.floor(secs / 60)}m ${secs % 60}s`)
    }
    compute()
    const id = setInterval(compute, 1000)
    return () => clearInterval(id)
  }, [startedAt, stopped])
  return elapsed
}

// ---------------------------------------------------------------------------
// Event log filter helpers
// ---------------------------------------------------------------------------

type EventFilter = "all" | "phases" | "llm" | "search" | "screening"

const FILTERS: { id: EventFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "phases", label: "Phases" },
  { id: "llm", label: "LLM Calls" },
  { id: "search", label: "Search" },
  { id: "screening", label: "Screening" },
]

function filterEvents(events: ReviewEvent[], filter: EventFilter): ReviewEvent[] {
  if (filter === "all") return events
  if (filter === "phases")
    return events.filter((e) => e.type === "phase_start" || e.type === "phase_done")
  if (filter === "llm") return events.filter((e) => e.type === "api_call")
  if (filter === "search") return events.filter((e) => e.type === "connector_result")
  if (filter === "screening") return events.filter((e) => e.type === "screening_decision")
  return events
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  icon: React.ElementType
  label: string
  value: string | number
  sub?: string
  accent?: string
  onClick?: () => void
}

function StatCard({ icon: Icon, label, value, sub, accent, onClick }: StatCardProps) {
  const Tag = onClick ? "button" : "div"
  return (
    <Tag
      type={onClick ? "button" : undefined}
      className={cn(
        "bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col gap-3 text-left w-full",
        onClick
          ? "cursor-pointer hover:border-violet-500/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/50"
          : "transition-colors",
      )}
      onClick={onClick}
      aria-label={onClick ? `${label}: ${value} -- click to view details` : undefined}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">{label}</span>
        <div className="flex items-center gap-1">
          <Icon className={cn("h-4 w-4", accent ?? "text-zinc-600")} />
          {onClick && <ArrowUpRight className="h-3 w-3 text-zinc-700" />}
        </div>
      </div>
      <div className="text-2xl font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="text-xs text-zinc-500">{sub}</div>}
    </Tag>
  )
}

// ---------------------------------------------------------------------------
// ActivityView
// ---------------------------------------------------------------------------

export interface ActivityViewProps {
  /** Live SSE events -- empty when viewing a historical run. */
  events: ReviewEvent[]
  /** SSE connection status. */
  status: string
  /** Backend run_id; used to fetch historical events when events is empty. */
  runId: string
  /** Whether we are showing a historical (completed) run vs a live one. */
  isDone: boolean
  costStats: CostStats
  startedAt: Date | null
  onCancel: () => void
  onCostTabClick: () => void
}

export function ActivityView({
  events,
  status,
  runId,
  isDone,
  costStats,
  startedAt,
  onCancel,
  onCostTabClick,
}: ActivityViewProps) {
  const [activeFilter, setActiveFilter] = useState<EventFilter>("all")

  // Historical event loading: when no live SSE events exist but the run is
  // done, fetch the persisted event log from the backend.
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const isHistoricalMode = isDone && events.length === 0 && Boolean(runId)

  const loadHistoricalEvents = useCallback(
    async (id: string) => {
      setLoadingHistory(true)
      setFetchError(null)
      try {
        const evs = await fetchRunEvents(id)
        setHistoricalEvents(evs)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        setFetchError(
          msg.toLowerCase().includes("failed to fetch")
            ? "Cannot reach backend. Start the server and try again."
            : msg,
        )
        setHistoricalEvents([])
      } finally {
        setLoadingHistory(false)
      }
    },
    [],
  )

  useEffect(() => {
    if (!isHistoricalMode || !runId) {
      setHistoricalEvents([])
      setFetchError(null)
      return
    }
    void loadHistoricalEvents(runId)
  }, [isHistoricalMode, runId, loadHistoricalEvents])

  const activeEvents = isHistoricalMode ? historicalEvents : events

  // For historical runs, compute cost stats from the loaded historical events
  // so the stat cards show real data instead of zeros.
  const historicalCostStats = useCostStats(historicalEvents)
  const displayCostStats: CostStats =
    isHistoricalMode && historicalCostStats.total_calls > 0
      ? historicalCostStats
      : costStats

  // Phase timeline state
  const phaseStates = useMemo(() => buildPhaseStates(activeEvents), [activeEvents])
  const liveElapsed = useElapsed(startedAt, status)
  const isRunning = status === "streaming" || status === "connecting"

  // For historical runs with no startedAt, derive elapsed from event timestamps.
  const elapsed =
    liveElapsed === "--" && isHistoricalMode
      ? derivedElapsedFromEvents(activeEvents)
      : liveElapsed

  const totalFound = activeEvents
    .filter((e) => e.type === "connector_result" && e.status === "success")
    .reduce((acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0), 0)

  const screened = activeEvents.filter((e) => e.type === "screening_decision").length

  const included = activeEvents.filter(
    (e) => e.type === "screening_decision" && e.decision === "include",
  ).length

  const phaseDoneCount = PHASE_ORDER.filter((p) => phaseStates[p]?.status === "done").length
  const totalPhases = PHASE_ORDER.length

  const filtered = filterEvents(activeEvents, activeFilter)

  return (
    <div className="flex flex-col gap-5">
      {/* Cancel / error controls */}
      {isRunning && (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={onCancel}
            className="border-zinc-700 text-zinc-300 hover:text-red-400 hover:border-red-500/40 gap-1.5"
          >
            <XCircle className="h-3.5 w-3.5" />
            Cancel Run
          </Button>
        </div>
      )}

      {status === "error" && (
        <div className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-medium">Review failed. </span>
            {(activeEvents.find((e) => e.type === "error") as { msg?: string } | undefined)?.msg ??
              "An unexpected error occurred."}
          </div>
        </div>
      )}

      {/* Stat cards -- 2 cols on mobile, 3 on sm, 5 on lg */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          icon={FileSearch}
          label="Papers Found"
          value={totalFound.toLocaleString()}
          sub="raw, before deduplication"
          accent="text-blue-400"
        />
        <StatCard
          icon={Filter}
          label="Screened"
          value={screened.toLocaleString()}
          sub="total decisions"
          accent="text-amber-400"
        />
        <StatCard
          icon={CheckCircle}
          label="Included"
          value={included.toLocaleString()}
          sub="passed screening"
          accent="text-emerald-400"
        />
        <StatCard
          icon={DollarSign}
          label="Cost"
          value={`$${displayCostStats.total_cost.toFixed(4)}`}
          sub={`${displayCostStats.total_calls} LLM calls`}
          accent="text-violet-400"
          onClick={onCostTabClick}
        />
        <StatCard
          icon={Clock}
          label="Elapsed"
          value={elapsed}
          sub={`${phaseDoneCount}/${totalPhases} phases done`}
          accent="text-zinc-400"
        />
      </div>

      {/* Phase timeline */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Layers className="h-3.5 w-3.5" />
          Phase Timeline
        </h3>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          {PHASE_ORDER.map((phase, i) => {
            const state = phaseStates[phase] ?? { status: "pending" as PhaseStatus }
            const label = PHASE_LABELS[phase] ?? phase
            const isLast = i === PHASE_ORDER.length - 1
            const progressPct =
              state.progress != null && state.progress.total > 0
                ? Math.round((state.progress.current / state.progress.total) * 100)
                : state.status === "done"
                  ? 100
                  : 0

            const durationStr =
              state.status === "done" && state.startedTs && state.doneTss
                ? fmtDuration(
                    new Date(state.doneTss).getTime() - new Date(state.startedTs).getTime(),
                  )
                : null

            return (
              <div
                key={phase}
                className={cn(
                  "flex items-center gap-4 px-4 py-3",
                  !isLast && "border-b border-zinc-800",
                )}
              >
                <div className="shrink-0">
                  {state.status === "done" ? (
                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                  ) : state.status === "running" ? (
                    <Loader className="h-4 w-4 text-violet-400 animate-spin" />
                  ) : (
                    <Circle className="h-4 w-4 text-zinc-700" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        "text-sm font-medium",
                        state.status === "done"
                          ? "text-zinc-200"
                          : state.status === "running"
                            ? "text-white"
                            : "text-zinc-600",
                      )}
                    >
                      {label}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      {durationStr && (
                        <span className="text-[10px] tabular-nums text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded font-mono">
                          {durationStr}
                        </span>
                      )}
                      {state.status !== "pending" && (
                        <span className="text-xs tabular-nums text-zinc-500">
                          {progressPct}%
                        </span>
                      )}
                    </div>
                  </div>
                  {state.status !== "pending" && (
                    <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-300",
                          state.status === "done" ? "bg-emerald-500" : "bg-violet-500",
                        )}
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  )}
                </div>
                {state.status === "running" && state.progress && (
                  <div className="shrink-0 text-xs text-zinc-500 tabular-nums">
                    {state.progress.current}/{state.progress.total}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Event log */}
      <div className="flex flex-col gap-3">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide flex items-center gap-2">
          Activity Log
        </h3>

        {fetchError && (
          <FetchError
            message={fetchError}
            onRetry={runId ? () => void loadHistoricalEvents(runId) : undefined}
          />
        )}

        {/* Inline filter chips + event count */}
        <div className="flex items-center gap-2 flex-wrap">
          <div
            role="toolbar"
            aria-label="Event filter"
            className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-0.5"
          >
            {FILTERS.map((f) => (
              <button
                key={f.id}
                onClick={() => setActiveFilter(f.id)}
                aria-pressed={activeFilter === f.id}
                aria-label={`${f.label} filter`}
                className={cn(
                  "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                  activeFilter === f.id
                    ? "bg-zinc-700 text-white"
                    : "text-zinc-500 hover:text-zinc-300",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          <span className="text-xs text-zinc-600">
            {loadingHistory ? (
              <span className="flex items-center gap-1.5 text-zinc-500">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading event log...
              </span>
            ) : (
              `${filtered.length} events${isHistoricalMode ? " (historical)" : ""}`
            )}
          </span>
        </div>

        {!loadingHistory && filtered.length === 0 && !fetchError && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl py-12 flex items-center justify-center">
            <p className="text-zinc-600 text-sm">Events will appear here once the review starts.</p>
          </div>
        )}

        {filtered.length > 0 && <LogStream events={filtered} />}
      </div>
    </div>
  )
}
