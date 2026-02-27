import { useCallback, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Loader,
  Loader2,
  XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { LogStream } from "@/components/LogStream"
import { FetchError } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { fetchRunEvents } from "@/lib/api"
import { PHASE_ORDER, PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Phase state helpers
// ---------------------------------------------------------------------------

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
      states[ev.phase] = {
        ...states[ev.phase],
        progress: { current: ev.current, total: ev.total },
      }
    }
  }
  return states
}

function fmtDuration(ms: number): string {
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

// ---------------------------------------------------------------------------
// Phase Stepper row
// ---------------------------------------------------------------------------

interface PhaseRowProps {
  phase: string
  state: PhaseState
  isLast: boolean
}

function PhaseRow({ phase, state, isLast }: PhaseRowProps) {
  const label = PHASE_LABELS[phase] ?? phase

  const durationStr =
    state.status === "done" && state.startedTs && state.doneTss
      ? fmtDuration(
          new Date(state.doneTss).getTime() - new Date(state.startedTs).getTime(),
        )
      : null

  const progressLabel =
    state.status === "running" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "done" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "done"
      ? "done"
      : null

  return (
    <div
      className={cn(
        "flex items-center gap-4 px-5 py-3.5",
        !isLast && "border-b border-zinc-800/60",
      )}
    >
      {/* Status icon */}
      <div className="shrink-0 w-5 flex justify-center">
        {state.status === "done" ? (
          <CheckCircle className="h-4 w-4 text-emerald-500" />
        ) : state.status === "running" ? (
          <Loader className="h-4 w-4 text-violet-400 animate-spin" />
        ) : (
          <Circle className="h-4 w-4 text-zinc-700" />
        )}
      </div>

      {/* Label */}
      <span
        className={cn(
          "flex-1 text-sm font-medium",
          state.status === "done"
            ? "text-zinc-300"
            : state.status === "running"
            ? "text-white"
            : "text-zinc-600",
        )}
      >
        {label}
      </span>

      {/* Progress chip */}
      {progressLabel && (
        <span
          className={cn(
            "text-xs tabular-nums font-mono px-2 py-0.5 rounded-full",
            state.status === "done"
              ? "text-emerald-400 bg-emerald-500/10"
              : "text-violet-400 bg-violet-500/10",
          )}
        >
          {progressLabel}
        </span>
      )}

      {/* Duration chip */}
      {durationStr && (
        <span className="text-[10px] tabular-nums text-zinc-600 bg-zinc-800 px-2 py-0.5 rounded font-mono shrink-0">
          {durationStr}
        </span>
      )}

      {/* Running indicator for phases with no progress yet */}
      {state.status === "running" && !state.progress && (
        <span className="text-[10px] text-violet-400/60 font-mono shrink-0">running...</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Event log filter
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
  events: ReviewEvent[]
  status: string
  runId: string
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
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const isHistoricalMode = isDone && events.length === 0 && Boolean(runId)

  const loadHistoricalEvents = useCallback(async (id: string) => {
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
  }, [])

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

      {/* Error banner */}
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

      {/* Phase stepper */}
      <div>
        <h3 className="label-caps font-semibold mb-3">
          Phase Timeline
        </h3>
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl overflow-hidden">
          {loadingHistory ? (
            <div className="px-5 py-4 space-y-3">
              {PHASE_ORDER.map((p) => (
                <Skeleton key={p} className="h-5 w-full" />
              ))}
            </div>
          ) : (
            PHASE_ORDER.map((phase, i) => (
              <PhaseRow
                key={phase}
                phase={phase}
                state={phaseStates[phase] ?? { status: "pending" }}
                isLast={i === PHASE_ORDER.length - 1}
              />
            ))
          )}
        </div>
      </div>

      {/* Event log */}
      <div className="flex flex-col gap-3">
        <h3 className="label-caps font-semibold">
          Activity Log
        </h3>

        {fetchError && (
          <FetchError
            message={fetchError}
            onRetry={runId ? () => void loadHistoricalEvents(runId) : undefined}
          />
        )}

        {/* Filter chips */}
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
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl py-12 flex items-center justify-center">
            <p className="text-zinc-600 text-sm">Events will appear here once the review starts.</p>
          </div>
        )}

        {filtered.length > 0 && (
          <LogStream events={filtered} autoScroll={activeFilter === "all"} />
        )}
      </div>
    </div>
  )
}
