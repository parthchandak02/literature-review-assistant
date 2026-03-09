import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  GripVertical,
  Loader,
  Loader2,
  Maximize2,
  Minimize2,
  Search,
  Square,
  XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LogStream } from "@/components/LogStream"
import type { LogStreamHandle } from "@/components/LogStream"
import { eventToLogLine } from "@/lib/logLine"
import { FetchError } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { fetchRunEvents, fetchWorkflowEvents } from "@/lib/api"
import { PHASE_ORDER, PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Phase state helpers
// ---------------------------------------------------------------------------

type PhaseStatus = "pending" | "running" | "done" | "error"

interface PhaseState {
  status: PhaseStatus
  progress?: { current: number; total: number }
  startedTs?: string
  doneTss?: string
}

function buildPhaseStates(events: ReviewEvent[], isRunComplete: boolean): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = { status: "running", startedTs: ev.ts }
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
  if (isRunComplete) {
    const hasTerminal =
      events.some((e) => e.type === "done" || e.type === "error" || e.type === "cancelled") ||
      Boolean(states.finalize?.status === "done")
    if (hasTerminal) {
      for (const phase of PHASE_ORDER) {
        const s = states[phase]
        if (s?.status === "running") {
          states[phase] = { ...s, status: "done", doneTss: s.doneTss ?? s.startedTs }
        }
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
// Shared status icon
// ---------------------------------------------------------------------------

function PhaseStatusIcon({ status }: { status: PhaseStatus }) {
  if (status === "done") return <CheckCircle className="h-4 w-4 text-emerald-500 shrink-0" />
  if (status === "running") return <Loader className="h-4 w-4 text-violet-400 animate-spin shrink-0" />
  if (status === "error") return <XCircle className="h-4 w-4 text-red-400 shrink-0" />
  return <Circle className="h-3.5 w-3.5 text-zinc-600 shrink-0" />
}

// ---------------------------------------------------------------------------
// Compact phase list (narrow left panel in "split" mode)
// ---------------------------------------------------------------------------

function CompactPhaseList({
  phaseStates,
  loading,
  onPhaseClick,
}: {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  onPhaseClick?: (phase: string) => void
}) {
  if (loading) {
    return (
      <div className="flex flex-col divide-y divide-zinc-800/60">
        {PHASE_ORDER.map((p) => (
          <div key={p} className="flex items-center gap-3 px-4 py-2.5">
            <Skeleton className="w-4 h-4 rounded-full shrink-0" />
            <Skeleton className="h-3 flex-1" />
            <Skeleton className="h-3 w-8" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col divide-y divide-zinc-800/60">
      {PHASE_ORDER.map((phase) => {
        const state = phaseStates[phase] ?? { status: "pending" as PhaseStatus }
        const label = PHASE_LABELS[phase] ?? phase

        const durationStr =
          state.status === "done" && state.startedTs && state.doneTss
            ? fmtDuration(new Date(state.doneTss).getTime() - new Date(state.startedTs).getTime())
            : null

        const progressLabel =
          (state.status === "running" || state.status === "done") && state.progress
            ? `${state.progress.current}/${state.progress.total}`
            : state.status === "running"
            ? "running..."
            : null

        const labelCls = cn(
          "text-sm flex-1 font-medium truncate",
          state.status === "done" && "text-zinc-300",
          state.status === "running" && "text-white",
          state.status === "error" && "text-red-400",
          state.status === "pending" && "text-zinc-600",
        )

        const isClickable = state.status !== "pending" && onPhaseClick
        return (
          <div
            key={phase}
            className={cn(
              "flex items-center gap-3 px-4 py-2.5 transition-colors",
              isClickable && "cursor-pointer hover:bg-zinc-800/40 active:bg-zinc-800/60",
            )}
            onClick={isClickable ? () => onPhaseClick(phase) : undefined}
            title={isClickable ? `Jump to ${label} in log` : undefined}
          >
            <PhaseStatusIcon status={state.status} />
            <span className={labelCls}>{label}</span>
            {progressLabel && (
              <span className={cn(
                "text-[11px] font-mono tabular-nums shrink-0",
                state.status === "running" ? "text-violet-400/80" : "text-emerald-500/80",
              )}>
                {progressLabel}
              </span>
            )}
            {durationStr && (
              <span className="text-[11px] font-mono tabular-nums text-zinc-600 shrink-0">
                {durationStr}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Horizontal stepper (full-width "timeline" mode)
// ---------------------------------------------------------------------------

interface PhaseStepProps {
  phase: string
  state: PhaseState
  isLast: boolean
}

function PhaseStep({ phase, state, isLast }: PhaseStepProps) {
  const label = PHASE_LABELS[phase] ?? phase

  const durationStr =
    state.status === "done" && state.startedTs && state.doneTss
      ? fmtDuration(new Date(state.doneTss).getTime() - new Date(state.startedTs).getTime())
      : null

  const subLabel =
    state.status === "running" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "done" && state.progress
      ? `${state.progress.current}/${state.progress.total}`
      : state.status === "running"
      ? "running..."
      : null

  const circleCls = cn(
    "w-8 h-8 rounded-full flex items-center justify-center border shrink-0",
    state.status === "done" && "bg-emerald-500/15 border-emerald-500/40 text-emerald-500",
    state.status === "running" && "bg-violet-500/15 border-violet-500/40 text-violet-400",
    state.status === "error" && "bg-red-500/15 border-red-500/40 text-red-400",
    state.status === "pending" && "bg-zinc-900 border-zinc-700 text-zinc-600",
  )

  const connectorCls = cn(
    "h-px shrink-0",
    state.status === "done" ? "bg-emerald-500/40" :
    state.status === "running" ? "bg-violet-500/30" :
    "bg-zinc-800",
  )

  const labelCls = cn(
    "text-[11px] text-center leading-tight font-medium px-0.5 mt-1.5",
    state.status === "done" && "text-zinc-300",
    state.status === "running" && "text-white",
    state.status === "error" && "text-red-400",
    state.status === "pending" && "text-zinc-600",
  )

  const subLabelCls = cn(
    "text-[10px] font-mono mt-0.5 tabular-nums",
    state.status === "running" ? "text-violet-400/80" : "text-emerald-500/80",
  )

  return (
    <div className="flex items-start">
      <div className="flex flex-col items-center w-[4.5rem] shrink-0">
        <div className={circleCls}>
          {state.status === "done" ? (
            <CheckCircle className="h-4 w-4" />
          ) : state.status === "running" ? (
            <Loader className="h-4 w-4 animate-spin" />
          ) : state.status === "error" ? (
            <XCircle className="h-4 w-4" />
          ) : (
            <Circle className="h-3.5 w-3.5" />
          )}
        </div>
        <span className={labelCls}>{label}</span>
        {subLabel && <span className={subLabelCls}>{subLabel}</span>}
        {durationStr && (
          <span className="text-[10px] font-mono tabular-nums text-zinc-600 mt-0.5">
            {durationStr}
          </span>
        )}
      </div>
      {!isLast && (
        <div className={cn("flex-1 mt-4", connectorCls)} style={{ minWidth: "1rem" }} />
      )}
    </div>
  )
}

function HorizontalStepperContent({
  phaseStates,
  loading,
}: {
  phaseStates: Record<string, PhaseState>
  loading: boolean
}) {
  if (loading) {
    return (
      <div className="flex items-start gap-2 px-5 py-5">
        {PHASE_ORDER.map((p, i) => (
          <div key={p} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1.5 w-[4.5rem] shrink-0">
              <Skeleton className="w-8 h-8 rounded-full" />
              <Skeleton className="h-2.5 w-10" />
            </div>
            {i < PHASE_ORDER.length - 1 && <div className="flex-1 mt-4 h-px bg-zinc-800" />}
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="px-5 py-5 overflow-x-auto">
      <div className="flex items-start min-w-max w-full">
        {PHASE_ORDER.map((phase, i) => (
          <PhaseStep
            key={phase}
            phase={phase}
            state={phaseStates[phase] ?? { status: "pending" }}
            isLast={i === PHASE_ORDER.length - 1}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Layout types and constants
// ---------------------------------------------------------------------------

type LayoutState = "split" | "timeline" | "log"

const MIN_LEFT_WIDTH = 200
const MAX_LEFT_WIDTH = 520
const DEFAULT_LEFT_WIDTH = 280

// ---------------------------------------------------------------------------
// ActivityView
// ---------------------------------------------------------------------------

export interface ActivityViewProps {
  events: ReviewEvent[]
  status: string
  runId: string
  workflowId?: string | null
  isDone: boolean
  onCancel: () => void
}

export function ActivityView({
  events,
  status,
  runId,
  workflowId,
  isDone,
  onCancel,
}: ActivityViewProps) {
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [layout, setLayout] = useState<LayoutState>("split")
  const [leftWidth, setLeftWidth] = useState(DEFAULT_LEFT_WIDTH)
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 767px)").matches,
  )

  const containerRef = useRef<HTMLDivElement>(null)
  const logRef = useRef<LogStreamHandle>(null)
  const isDragging = useRef(false)

  // Track mobile breakpoint (md = 768px) -- on mobile, stack panels vertically.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)")
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  // Drag-to-resize divider
  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isDragging.current = true
    document.body.style.cursor = "col-resize"
    document.body.style.userSelect = "none"

    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const newWidth = Math.max(MIN_LEFT_WIDTH, Math.min(MAX_LEFT_WIDTH, ev.clientX - rect.left))
      setLeftWidth(newWidth)
    }

    const handleMouseUp = () => {
      isDragging.current = false
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
  }, [])

  const isHistoricalMode = isDone && events.length === 0 && Boolean(runId)

  const loadHistoricalEvents = useCallback(
    async (id: string, wfId: string | null | undefined) => {
      setLoadingHistory(true)
      setFetchError(null)
      try {
        let evs = await fetchRunEvents(id)
        if (evs.length === 0 && wfId && wfId !== id) {
          evs = await fetchWorkflowEvents(wfId)
        }
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
    void loadHistoricalEvents(runId, workflowId)
  }, [isHistoricalMode, runId, workflowId, loadHistoricalEvents])

  const [searchQuery, setSearchQuery] = useState("")
  const activeEvents = isHistoricalMode ? historicalEvents : events
  const phaseStates = useMemo(
    () => buildPhaseStates(activeEvents, isDone),
    [activeEvents, isDone],
  )
  const isRunning = status === "streaming" || status === "connecting"
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return activeEvents
    const q = searchQuery.trim().toLowerCase()
    return activeEvents.filter((ev) => eventToLogLine(ev).text.toLowerCase().includes(q))
  }, [activeEvents, searchQuery])

  const eventCountLabel = loadingHistory
    ? null
    : searchQuery.trim()
    ? `${filtered.length} of ${activeEvents.length} events`
    : `${filtered.length} events${isHistoricalMode ? " (historical)" : ""}`

  return (
    <div className="flex flex-col gap-4">
      {/* Live run controls */}
      {isRunning && (
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5 text-xs">
            {status === "connecting" ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-400" />
                <span className="text-violet-400">Connecting to event stream...</span>
              </>
            ) : (
              <>
                <span className="relative flex h-2 w-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
                </span>
                <span className="text-violet-400">Live stream active</span>
              </>
            )}
          </div>
          <Button
            size="sm"
            onClick={onCancel}
            className="bg-red-600 hover:bg-red-500 text-white gap-1.5 shrink-0"
          >
            <Square className="h-3.5 w-3.5 fill-white" />
            Stop
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
              (activeEvents.find((e) => e.type === "done") as { outputs?: { error?: string } } | undefined)?.outputs?.error ??
              "An unexpected error occurred."}
          </div>
        </div>
      )}

      {/* Split panel row -- stacks vertically on mobile, side-by-side on md+ */}
      <div
        ref={containerRef}
        className={cn("flex", isMobile ? "flex-col gap-3" : "flex-row")}
        style={isMobile ? undefined : { minHeight: "480px", alignItems: "stretch" }}
      >
        {/* ---- Phase Timeline Panel ---- */}
        {layout !== "log" && (
          <div
            className="flex flex-col min-w-0"
            style={
              isMobile
                ? { minHeight: "240px" }
                : layout === "split"
                  ? { width: leftWidth, flexShrink: 0 }
                  : { flex: 1 }
            }
          >
            <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
              <div className="flex items-center justify-between px-4 h-11 border-b border-zinc-800 shrink-0">
                <span className="label-caps">Phase Timeline</span>
                <button
                  onClick={() => setLayout(layout === "timeline" ? "split" : "timeline")}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors p-0.5 rounded"
                  title={layout === "timeline" ? "Restore split view" : "Expand timeline"}
                >
                  {layout === "timeline"
                    ? <Minimize2 className="h-3.5 w-3.5" />
                    : <Maximize2 className="h-3.5 w-3.5" />
                  }
                </button>
              </div>
              <div className="flex-1 overflow-y-auto min-h-0">
                {layout === "split" ? (
                  <CompactPhaseList
                    phaseStates={phaseStates}
                    loading={loadingHistory}
                    onPhaseClick={(phase) => {
                      logRef.current?.scrollToPhase(phase)
                    }}
                  />
                ) : (
                  <HorizontalStepperContent phaseStates={phaseStates} loading={loadingHistory} />
                )}
              </div>
            </div>
          </div>
        )}

        {/* ---- Drag handle (only in split mode, only on desktop) ---- */}
        {layout === "split" && !isMobile && (
          <div
            className="flex items-center justify-center w-3 shrink-0 cursor-col-resize group relative"
            onMouseDown={handleDividerMouseDown}
          >
            {/* Invisible hit area for easier grabbing */}
            <div className="absolute inset-y-0 -inset-x-1 z-10" />
            {/* Visual indicator: thin line that brightens on hover, dot on center */}
            <div className="flex flex-col items-center gap-1 relative z-20 h-full justify-center">
              <div className="w-px flex-1 bg-zinc-800 group-hover:bg-violet-500/40 transition-colors" />
              <GripVertical className="h-4 w-4 text-zinc-700 group-hover:text-violet-400 transition-colors shrink-0" />
              <div className="w-px flex-1 bg-zinc-800 group-hover:bg-violet-500/40 transition-colors" />
            </div>
          </div>
        )}

        {/* ---- Activity Log Panel ---- */}
        {layout !== "timeline" && (
          <div
            className="flex flex-col min-w-0"
            style={isMobile ? { minHeight: "320px" } : { flex: 1 }}
          >
            <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
              {/* Header */}
              <div className="flex items-center gap-2 px-4 h-11 border-b border-zinc-800 shrink-0 overflow-hidden">
                <span className="label-caps shrink-0">Activity Log</span>

                {loadingHistory ? (
                  <span className="flex items-center gap-1.5 text-xs text-zinc-500">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Loading...
                  </span>
                ) : eventCountLabel ? (
                  <span className="text-xs text-zinc-600 tabular-nums shrink-0">
                    {eventCountLabel}
                  </span>
                ) : null}

                <div className="relative flex-1 min-w-0">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500 pointer-events-none" />
                  <Input
                    type="text"
                    placeholder="Search log..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8 h-7 text-xs bg-transparent border-zinc-800 w-full"
                  />
                </div>

                <button
                  onClick={() => setLayout(layout === "log" ? "split" : "log")}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors p-0.5 rounded shrink-0"
                  title={layout === "log" ? "Restore split view" : "Expand log"}
                >
                  {layout === "log"
                    ? <Minimize2 className="h-3.5 w-3.5" />
                    : <Maximize2 className="h-3.5 w-3.5" />
                  }
                </button>
              </div>

              {/* Log body - scrollable */}
              <div className="flex-1 overflow-y-auto min-h-0">
                {fetchError && (
                  <div className="p-4">
                    <FetchError
                      message={fetchError}
                      onRetry={runId ? () => void loadHistoricalEvents(runId, workflowId) : undefined}
                    />
                  </div>
                )}

                {!loadingHistory && filtered.length === 0 && !fetchError && (
                  <div className="py-12 flex items-center justify-center">
                    <p className="text-zinc-600 text-sm">
                      Events will appear here once the review starts.
                    </p>
                  </div>
                )}

                {filtered.length > 0 && (
                  <LogStream ref={logRef} events={filtered} autoScroll={!searchQuery.trim()} />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
