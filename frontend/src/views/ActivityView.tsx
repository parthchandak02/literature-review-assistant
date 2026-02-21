import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle,
  Circle,
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
  onCancel: () => void
}

export function ActivityView({
  events,
  status,
  runId,
  isDone,
  onCancel,
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

  const phaseStates = useMemo(() => buildPhaseStates(activeEvents), [activeEvents])
  const isRunning = status === "streaming" || status === "connecting"

  const filtered = filterEvents(activeEvents, activeFilter)

  return (
    <div className="flex flex-col gap-5">
      {/* Cancel / connecting controls */}
      {isRunning && (
        <div className="flex items-center justify-between">
          {status === "connecting" ? (
            <div className="flex items-center gap-1.5 text-xs text-violet-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Connecting to event stream...
            </div>
          ) : (
            <div />
          )}
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
            ) : activeFilter === "all" ? (
              `${filtered.length} events${isHistoricalMode ? " (historical)" : ""}`
            ) : (
              `${filtered.length} of ${activeEvents.length} events`
            )}
          </span>
        </div>

        {!loadingHistory && filtered.length === 0 && !fetchError && (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl py-12 flex items-center justify-center">
            <p className="text-zinc-600 text-sm">Events will appear here once the review starts.</p>
          </div>
        )}

        {filtered.length > 0 && <LogStream events={filtered} autoScroll={activeFilter === "all"} />}
      </div>
    </div>
  )
}
