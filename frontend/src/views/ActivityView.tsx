import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Loader,
  Loader2,
  Search,
  Square,
  XCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LogStream } from "@/components/LogStream"
import type { LogStreamHandle } from "@/components/LogStream"
import { eventToLogEntry } from "@/lib/logLine"
import { FetchError } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { fetchRunEvents, fetchWorkflowEvents } from "@/lib/api"
import { PHASE_ORDER, PHASE_LABELS, RESUME_PHASE_ORDER } from "@/lib/constants"
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
// Horizontal stepper (full-width "timeline" mode)
// ---------------------------------------------------------------------------

interface PhaseStepProps {
  phase: string
  state: PhaseState
  isLast: boolean
  isResumeSelectable?: boolean
  isArmed?: boolean
  inResumeRange?: boolean
  isRangeStart?: boolean
  isRangeEnd?: boolean
  onResumeTap?: (phase: string) => void
}

function PhaseStep({
  phase,
  state,
  isLast,
  isResumeSelectable = false,
  isArmed = false,
  inResumeRange = false,
  isRangeStart = false,
  isRangeEnd = false,
  onResumeTap,
}: PhaseStepProps) {
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
    <div className="relative flex items-start py-1">
      {inResumeRange && (
        <div
          className={cn(
            "absolute left-0 right-0 top-1 h-14 bg-amber-500/10",
            isRangeStart && "rounded-l-md",
            isRangeEnd && "rounded-r-md",
          )}
          aria-hidden
        />
      )}
      <div className="flex flex-col items-center w-[4.5rem] shrink-0">
        <button
          type="button"
          onClick={() => {
            if (!isResumeSelectable || !onResumeTap) return
            onResumeTap(phase)
          }}
          disabled={!isResumeSelectable}
          className={cn(
            circleCls,
            "relative transition-colors",
            isResumeSelectable && "cursor-pointer hover:border-amber-500/50",
            isArmed && "border-amber-400 bg-amber-500/20 text-amber-300",
          )}
          title={isResumeSelectable ? "Tap once to arm resume, tap again to confirm" : undefined}
        >
          {state.status === "done" ? (
            <CheckCircle className="h-4 w-4" />
          ) : state.status === "running" ? (
            <Loader className="h-4 w-4 animate-spin" />
          ) : state.status === "error" ? (
            <XCircle className="h-4 w-4" />
          ) : (
            <Circle className="h-3.5 w-3.5" />
          )}
        </button>
        <span className={labelCls}>{label}</span>
        {subLabel && <span className={subLabelCls}>{subLabel}</span>}
        {durationStr && (
          <span className="text-[10px] font-mono tabular-nums text-zinc-600 mt-0.5">
            {durationStr}
          </span>
        )}
      </div>
      {!isLast && (
        <div className={cn("relative flex-1 mt-4", connectorCls)} style={{ minWidth: "1rem" }} />
      )}
    </div>
  )
}

function HorizontalStepperContent({
  phaseStates,
  loading,
  canResumeFromTimeline,
  armedResumePhase,
  armedResumeStartIdx,
  onResumeTap,
}: {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  canResumeFromTimeline: boolean
  armedResumePhase: string | null
  armedResumeStartIdx: number
  onResumeTap: (phase: string) => void
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
        {PHASE_ORDER.map((phase, i) => {
          const inResumeRange = armedResumeStartIdx >= 0 && i >= armedResumeStartIdx
          const isRangeStart = inResumeRange && i === armedResumeStartIdx
          const isRangeEnd = inResumeRange && i === PHASE_ORDER.length - 1
          return (
            <PhaseStep
              key={phase}
              phase={phase}
              state={phaseStates[phase] ?? { status: "pending" }}
              isLast={i === PHASE_ORDER.length - 1}
              isResumeSelectable={canResumeFromTimeline && RESUME_PHASE_ORDER.includes(phase as (typeof RESUME_PHASE_ORDER)[number])}
              isArmed={armedResumePhase === phase}
              inResumeRange={inResumeRange}
              isRangeStart={isRangeStart}
              isRangeEnd={isRangeEnd}
              onResumeTap={onResumeTap}
            />
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ActivityView
// ---------------------------------------------------------------------------

export interface ActivityViewProps {
  events: ReviewEvent[]
  prefetchedHistoricalEvents?: ReviewEvent[] | null
  historicalEventsLoading?: boolean
  status: string
  runId: string
  workflowId?: string | null
  historicalStatus?: string | null
  isDone: boolean
  onCancel: () => void
  onResumeFromPhase?: (phase: string) => Promise<void>
}

export function ActivityView({
  events,
  prefetchedHistoricalEvents = null,
  historicalEventsLoading = false,
  status,
  runId,
  workflowId,
  historicalStatus,
  isDone,
  onCancel,
  onResumeFromPhase,
}: ActivityViewProps) {
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [armedResumePhase, setArmedResumePhase] = useState<string | null>(null)
  const [resumeHint, setResumeHint] = useState<string | null>(null)
  const logRef = useRef<LogStreamHandle>(null)

  const hasPrefetchedHistorical = prefetchedHistoricalEvents != null
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
    if (hasPrefetchedHistorical) {
      return
    }
    void loadHistoricalEvents(runId, workflowId)
  }, [isHistoricalMode, runId, workflowId, loadHistoricalEvents, hasPrefetchedHistorical])

  const [searchQuery, setSearchQuery] = useState("")
  const activeHistoricalEvents = hasPrefetchedHistorical ? (prefetchedHistoricalEvents ?? []) : historicalEvents
  const activeEvents = isHistoricalMode ? activeHistoricalEvents : events
  const effectiveLoadingHistory = hasPrefetchedHistorical ? historicalEventsLoading : loadingHistory
  const phaseStates = useMemo(
    () => buildPhaseStates(activeEvents, isDone),
    [activeEvents, isDone],
  )
  const isRunning = status === "streaming" || status === "connecting"
  const normalizedHistoricalStatus = (historicalStatus ?? "").toLowerCase()
  const canResumeFromTimeline =
    Boolean(onResumeFromPhase) &&
    normalizedHistoricalStatus !== "awaiting_review"
  const armedResumeStartIdx = useMemo(() => {
    if (!armedResumePhase) return -1
    return PHASE_ORDER.indexOf(armedResumePhase as (typeof PHASE_ORDER)[number])
  }, [armedResumePhase])

  useEffect(() => {
    if (!armedResumePhase) return
    const timer = setTimeout(() => {
      setArmedResumePhase(null)
      setResumeHint(null)
    }, 8000)
    return () => clearTimeout(timer)
  }, [armedResumePhase])

  async function handlePhaseResumeTap(phase: string) {
    if (!canResumeFromTimeline) return
    if (!RESUME_PHASE_ORDER.includes(phase as (typeof RESUME_PHASE_ORDER)[number])) return
    if (armedResumePhase !== phase) {
      setArmedResumePhase(phase)
      setResumeHint(`Tap ${PHASE_LABELS[phase] ?? phase} again to confirm resume`)
      return
    }
    setResumeHint(`Resuming from ${PHASE_LABELS[phase] ?? phase}...`)
    try {
      await onResumeFromPhase?.(phase)
      setArmedResumePhase(null)
      setResumeHint(null)
    } catch {
      setResumeHint("Resume failed. Tap a phase again to retry.")
      setArmedResumePhase(null)
    }
  }
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return activeEvents.filter((ev) => {
      const entry = eventToLogEntry(ev)
      if (q && !entry.text.toLowerCase().includes(q)) return false
      return true
    })
  }, [activeEvents, searchQuery])

  const eventCountLabel = effectiveLoadingHistory
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

      <div className="flex flex-col gap-3 min-h-[480px]">
        <div className="card-surface overflow-hidden flex flex-col">
          <div className="glass-toolbar flex items-center justify-between px-4 h-11 border-b border-zinc-800/70 shrink-0">
            <span className="label-caps">Phase Timeline</span>
            {canResumeFromTimeline && (
              <span className="text-[11px] text-zinc-500">
                {resumeHint ?? "Tap a phase once, tap again to resume from it"}
              </span>
            )}
          </div>
          <HorizontalStepperContent
            phaseStates={phaseStates}
            loading={effectiveLoadingHistory}
            canResumeFromTimeline={canResumeFromTimeline}
            armedResumePhase={armedResumePhase}
            armedResumeStartIdx={armedResumeStartIdx}
            onResumeTap={handlePhaseResumeTap}
          />
        </div>

        <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
          <div className="glass-toolbar flex items-center gap-2 px-4 h-11 border-b border-zinc-800/70 shrink-0 overflow-hidden">
            <span className="label-caps shrink-0">Activity Log</span>

            {effectiveLoadingHistory ? (
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
          </div>

          <div className="flex-1 overflow-y-auto min-h-0">
            {fetchError && (
              <div className="p-4">
                <FetchError
                  message={fetchError}
                  onRetry={runId ? () => void loadHistoricalEvents(runId, workflowId) : undefined}
                />
              </div>
            )}

            {!effectiveLoadingHistory && filtered.length === 0 && !fetchError && (
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
    </div>
  )
}
