import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  CheckCircle,
  Circle,
  Search,
  XCircle,
} from "lucide-react"
import { Input } from "@/components/ui/input"
import { LogStream } from "@/components/LogStream"
import type { LogStreamHandle } from "@/components/LogStream"
import { eventToLogEntry } from "@/lib/logLine"
import { FetchError, Spinner } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { fetchHistoricalReviewEvents } from "@/lib/api"
import { shouldShowHistoricalLoading, shouldUsePrefetchedHistorical } from "@/lib/runSelection"
import { PHASE_ORDER, PHASE_LABELS, PHASE_MILESTONES, RESUME_PHASE_ORDER } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { cn } from "@/lib/utils"
import { ViewToolbar } from "@/components/ui/view-toolbar"

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

function buildPhaseStates(events: ReviewEvent[], workflowCompleted: boolean): Record<string, PhaseState> {
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
    } else if (ev.type === "progress") {
      // Progress may be the first marker seen for a phase after UI event capping.
      // Initialize as running so timeline state does not look stuck.
      const prev = states[ev.phase]
      states[ev.phase] = {
        status: prev?.status ?? "running",
        startedTs: prev?.startedTs,
        doneTss: prev?.doneTss,
        progress: { current: ev.current, total: ev.total },
      }
    }
  }
  if (workflowCompleted) {
    for (const phase of PHASE_ORDER) {
      const s = states[phase]
      if (s?.status === "running") {
        states[phase] = { ...s, status: "done", doneTss: s.doneTss ?? s.startedTs }
      }
    }
  }
  return states
}

function isPhaseEligibleForResume(
  phase: string,
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): boolean {
  if (!RESUME_PHASE_ORDER.includes(phase as (typeof RESUME_PHASE_ORDER)[number])) return false
  const idx = RESUME_PHASE_ORDER.indexOf(phase as (typeof RESUME_PHASE_ORDER)[number])
  if (idx < 0) return false
  if (completedWorkflow) {
    return phaseStates[phase]?.status === "done"
  }
  for (let i = 0; i < idx; i++) {
    const prereq = RESUME_PHASE_ORDER[i]
    if (phaseStates[prereq]?.status !== "done") return false
  }
  const state = phaseStates[phase]
  return Boolean(state && (state.status === "done" || state.status === "running" || state.status === "error"))
}

function buildMilestoneState(
  phases: readonly string[],
  phaseStates: Record<string, PhaseState>,
  completedWorkflow: boolean,
): PhaseState {
  const states = phases.map((phase) => phaseStates[phase] ?? { status: "pending" as const })
  if (states.some((s) => s.status === "error")) {
    return { status: "error" }
  }
  const allDone = states.every((s) => s.status === "done")
  if (allDone) {
    const firstStarted = states.find((s) => s.startedTs)?.startedTs
    const lastDone = [...states].reverse().find((s) => s.doneTss)?.doneTss
    return { status: "done", startedTs: firstStarted, doneTss: lastDone }
  }
  if (completedWorkflow) {
    const completedState = states.find((s) => s.status === "done" || s.status === "running")
    if (completedState) {
      return {
        status: "done",
        progress: completedState.progress,
        startedTs: completedState.startedTs,
        doneTss: completedState.doneTss ?? completedState.startedTs,
      }
    }
    return { status: "pending" }
  }
  const runningState = states.find((s) => s.status === "running" || s.status === "done")
  if (runningState) {
    return {
      status: "running",
      progress: runningState.progress,
      startedTs: runningState.startedTs,
      doneTss: runningState.doneTss,
    }
  }
  return { status: "pending" }
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
  label?: string
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
  label,
  isResumeSelectable = false,
  isArmed = false,
  inResumeRange = false,
  isRangeStart = false,
  isRangeEnd = false,
  onResumeTap,
}: PhaseStepProps) {
  const stepLabel = label ?? PHASE_LABELS[phase] ?? phase

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
    "w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center border shrink-0",
    state.status === "done" && "bg-intent-success-subtle border-intent-success-border text-intent-success",
    state.status === "running" && "bg-intent-active-subtle border-intent-active-border text-intent-active",
    state.status === "error" && "bg-intent-danger-subtle border-intent-danger-border text-intent-danger",
    state.status === "pending" && "bg-card border-border text-muted",
  )

  const connectorCls = cn(
    "h-px shrink-0",
    state.status === "done" ? "bg-intent-success" :
    state.status === "running" ? "bg-intent-active" :
    "bg-border",
  )

  const labelCls = cn(
    "text-[10px] sm:text-[11px] text-center leading-tight font-medium px-0 mt-1.5",
    state.status === "done" && "text-foreground",
    state.status === "running" && "text-intent-active",
    state.status === "error" && "text-intent-danger",
    state.status === "pending" && "text-muted",
  )

  const subLabelCls = cn(
    "text-[9px] sm:text-[10px] font-mono mt-0.5 tabular-nums text-center",
    state.status === "running" ? "text-intent-active" : "text-intent-success",
  )

  return (
    <div className="relative flex flex-1 min-w-0 items-start py-1">
      {inResumeRange && (
        <div
          className={cn(
            "absolute left-0 right-0 top-1 h-14 sm:h-14 bg-intent-warning-subtle",
            isRangeStart && "rounded-l-md",
            isRangeEnd && "rounded-r-md",
          )}
          aria-hidden
        />
      )}
      <div className="flex flex-col items-center w-full shrink-0">
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
            isResumeSelectable && "cursor-pointer hover:border-intent-warning-border",
            isArmed && "border-intent-warning bg-intent-warning-subtle text-intent-warning",
          )}
          title={isResumeSelectable ? "Tap once to arm resume, tap again to confirm" : undefined}
        >
          {state.status === "done" ? (
            <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : state.status === "running" ? (
            <Spinner size="md" />
          ) : state.status === "error" ? (
            <XCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : (
            <Circle className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          )}
        </button>
        <span className={labelCls}>{stepLabel}</span>
        {subLabel && <span className={subLabelCls}>{subLabel}</span>}
        {durationStr && (
          <span className="text-[9px] sm:text-[10px] font-mono tabular-nums text-muted mt-0.5 text-center">
            {durationStr}
          </span>
        )}
      </div>
      {!isLast && (
        <div className={cn("relative flex-1 mt-3.5 sm:mt-4", connectorCls)} style={{ minWidth: "0.35rem" }} />
      )}
    </div>
  )
}

function HorizontalStepperContent({
  phaseStates,
  loading,
  completedWorkflow,
  canResumeFromTimeline,
  isPhaseResumeSelectable,
  armedResumePhase,
  armedMilestoneStartIdx,
  onResumeTap,
}: {
  phaseStates: Record<string, PhaseState>
  loading: boolean
  completedWorkflow: boolean
  canResumeFromTimeline: boolean
  isPhaseResumeSelectable: (phase: string) => boolean
  armedResumePhase: string | null
  armedMilestoneStartIdx: number
  onResumeTap: (phase: string) => void
}) {
  if (loading) {
    return (
      <div className="data-surface flex items-start gap-1 px-3 py-4 sm:px-4 sm:py-5">
        {PHASE_MILESTONES.map((milestone, i) => (
          <div key={milestone.key} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1.5 w-full shrink-0">
              <Skeleton className="w-7 h-7 sm:w-8 sm:h-8 rounded-full" />
              <Skeleton className="h-2.5 w-8 sm:w-10" />
            </div>
            {i < PHASE_MILESTONES.length - 1 && <div className="flex-1 mt-3.5 sm:mt-4 h-px bg-border" />}
          </div>
        ))}
      </div>
    )
  }
  return (
    <div className="data-surface px-3 py-4 sm:px-4 sm:py-5 overflow-hidden">
      <div className="flex items-start w-full gap-0.5 sm:gap-1">
        {PHASE_MILESTONES.map((milestone, i) => {
          const targetPhase = milestone.phases.find((phase) => isPhaseResumeSelectable(phase)) ?? milestone.phases[0]
          const inResumeRange = armedMilestoneStartIdx >= 0 && i >= armedMilestoneStartIdx
          const isRangeStart = inResumeRange && i === armedMilestoneStartIdx
          const isRangeEnd = inResumeRange && i === PHASE_MILESTONES.length - 1
          return (
            <PhaseStep
              key={milestone.key}
              phase={targetPhase}
              label={milestone.label}
              state={buildMilestoneState(milestone.phases, phaseStates, completedWorkflow)}
              isLast={i === PHASE_MILESTONES.length - 1}
              isResumeSelectable={canResumeFromTimeline && isPhaseResumeSelectable(targetPhase)}
              isArmed={armedResumePhase === targetPhase}
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
  /** When true, an empty event list can fall back to persisted history. */
  allowHistoricalFallback?: boolean
  /** True while history attach is in flight — use workflow replay only. */
  attachPending?: boolean
  status: string
  runId: string
  workflowId?: string | null
  historicalStatus?: string | null
  onResumeFromPhase?: (phase: string) => Promise<void>
  resumeModeActive?: boolean
}

export function ActivityView({
  events,
  prefetchedHistoricalEvents = null,
  historicalEventsLoading = false,
  allowHistoricalFallback = false,
  attachPending = false,
  status,
  runId,
  workflowId,
  historicalStatus,
  onResumeFromPhase,
  resumeModeActive = false,
}: ActivityViewProps) {
  const [historicalEvents, setHistoricalEvents] = useState<ReviewEvent[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [armedResumePhase, setArmedResumePhase] = useState<string | null>(null)
  const [resumeHint, setResumeHint] = useState<string | null>(null)
  const [isSubmittingResume, setIsSubmittingResume] = useState(false)
  const logRef = useRef<LogStreamHandle>(null)

  const hasPrefetchedHistorical = shouldUsePrefetchedHistorical(prefetchedHistoricalEvents)
  const isFallbackMode = allowHistoricalFallback && events.length === 0 && Boolean(runId)

  const loadHistoricalEvents = useCallback(
    async (id: string, wfId: string | null | undefined, pending: boolean) => {
      setLoadingHistory(true)
      setFetchError(null)
      try {
        const evs = await fetchHistoricalReviewEvents(wfId, id, { attachPending: pending })
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
    if (!isFallbackMode || !runId) {
      setHistoricalEvents([])
      setFetchError(null)
      return
    }
    if (hasPrefetchedHistorical || historicalEventsLoading) {
      return
    }
    let cancelled = false
    setLoadingHistory(true)
    setFetchError(null)
    ;(async () => {
      try {
        const evs = await fetchHistoricalReviewEvents(workflowId, runId, { attachPending })
        if (!cancelled) setHistoricalEvents(evs)
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e)
          setFetchError(
            msg.toLowerCase().includes("failed to fetch")
              ? "Cannot reach backend. Start the server and try again."
              : msg,
          )
          setHistoricalEvents([])
        }
      } finally {
        if (!cancelled) setLoadingHistory(false)
      }
    })()
    return () => {
      cancelled = true
      setLoadingHistory(false)
    }
  }, [isFallbackMode, runId, workflowId, hasPrefetchedHistorical, historicalEventsLoading, attachPending])

  const [searchQuery, setSearchQuery] = useState("")
  const activeHistoricalEvents = hasPrefetchedHistorical ? (prefetchedHistoricalEvents ?? []) : historicalEvents
  const activeEvents = isFallbackMode ? activeHistoricalEvents : events
  const effectiveLoadingHistory = shouldShowHistoricalLoading(
    historicalEventsLoading,
    loadingHistory,
    activeEvents.length,
  )
  const normalizedHistoricalStatus = (historicalStatus ?? "").toLowerCase()
  const completedWorkflow =
    normalizedHistoricalStatus === "completed" ||
    normalizedHistoricalStatus === "done" ||
    status === "done"
  const phaseStates = useMemo(
    () => buildPhaseStates(activeEvents, completedWorkflow),
    [activeEvents, completedWorkflow],
  )
  const isRunning = status === "streaming" || status === "connecting"
  const resumeBlockedReason = (() => {
    if (!onResumeFromPhase) return "Resume controls are not available for this run."
    if (
      isRunning ||
      normalizedHistoricalStatus === "running" ||
      normalizedHistoricalStatus === "streaming" ||
      normalizedHistoricalStatus === "connecting"
    ) {
      return "Resume is unavailable while this workflow is running."
    }
    if (normalizedHistoricalStatus === "awaiting_review") {
      return "Approve screening first before resuming from later phases."
    }
    return null
  })()
  const canResumeEligibility = resumeBlockedReason === null
  const canResumeFromTimeline = resumeModeActive && canResumeEligibility
  const isPhaseResumeSelectable = useCallback(
    (phase: string) => isPhaseEligibleForResume(phase, phaseStates, completedWorkflow),
    [phaseStates, completedWorkflow],
  )
  const armedMilestoneStartIdx = useMemo(() => {
    if (!armedResumePhase) return -1
    return PHASE_MILESTONES.findIndex((milestone) =>
      milestone.phases.some((phase) => phase === armedResumePhase),
    )
  }, [armedResumePhase])

  useEffect(() => {
    if (!armedResumePhase) return
    const timer = setTimeout(() => {
      setArmedResumePhase(null)
      setResumeHint(null)
    }, 8000)
    return () => clearTimeout(timer)
  }, [armedResumePhase])

  useEffect(() => {
    if (resumeModeActive) return
    setArmedResumePhase(null)
    setResumeHint(null)
  }, [resumeModeActive])

  async function handlePhaseResumeTap(phase: string) {
    if (!canResumeFromTimeline || isSubmittingResume) return
    if (!isPhaseResumeSelectable(phase)) return
    if (armedResumePhase !== phase) {
      setArmedResumePhase(phase)
      setResumeHint(`Tap ${PHASE_LABELS[phase] ?? phase} again to confirm resume`)
      return
    }
    setResumeHint(`Resuming from ${PHASE_LABELS[phase] ?? phase}...`)
    setIsSubmittingResume(true)
    try {
      await onResumeFromPhase?.(phase)
      setArmedResumePhase(null)
      setResumeHint(null)
    } catch {
      setResumeHint("Resume failed. Tap a phase again to retry.")
      setArmedResumePhase(null)
    } finally {
      setIsSubmittingResume(false)
    }
  }
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return activeEvents
    return activeEvents.filter((ev) => eventToLogEntry(ev).text.toLowerCase().includes(q))
  }, [activeEvents, searchQuery])

  const eventCountLabel = effectiveLoadingHistory
    ? null
    : searchQuery.trim()
    ? `${filtered.length} of ${activeEvents.length} events`
    : `${filtered.length} events${isFallbackMode ? " (historical)" : ""}`

  return (
    <div className="flex flex-col gap-4">
      {/* Error banner */}
      {status === "error" && (
        <div className="flex items-start gap-2.5 bg-intent-danger-subtle border border-intent-danger-border rounded-xl px-4 py-3 text-sm text-intent-danger">
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
          <ViewToolbar
            title={<span className="label-caps">Phase Timeline</span>}
            actions={
              resumeModeActive ? (
                <span className="text-[11px] text-muted">
                  {resumeHint ?? (canResumeEligibility ? "Tap a phase once, tap again to resume from it" : resumeBlockedReason)}
                </span>
              ) : canResumeEligibility ? (
                <span className="text-[11px] text-muted">
                  Use Resume from last checkpoint in the sidebar
                </span>
              ) : null
            }
          />
          <HorizontalStepperContent
            phaseStates={phaseStates}
            loading={effectiveLoadingHistory}
            completedWorkflow={completedWorkflow}
            canResumeFromTimeline={canResumeFromTimeline}
            isPhaseResumeSelectable={isPhaseResumeSelectable}
            armedResumePhase={armedResumePhase}
            armedMilestoneStartIdx={armedMilestoneStartIdx}
            onResumeTap={handlePhaseResumeTap}
          />
        </div>

        <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
          <ViewToolbar className="overflow-hidden gap-2">
            <span className="label-caps shrink-0">Activity Log</span>

            {effectiveLoadingHistory ? (
              <span className="flex items-center gap-1.5 text-xs text-muted">
                <Spinner size="sm" />
                Loading...
              </span>
            ) : eventCountLabel ? (
              <span className="text-xs text-muted tabular-nums shrink-0">
                {eventCountLabel}
              </span>
            ) : null}

            <div className="relative flex-1 min-w-0">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted pointer-events-none" />
              <Input
                type="text"
                placeholder="Search log..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-7 text-xs bg-transparent border-border w-full"
              />
            </div>
          </ViewToolbar>

          <div className="data-surface flex-1 overflow-y-auto min-h-0">
            {fetchError && (
              <div className="p-4">
                <FetchError
                  message={fetchError}
                  onRetry={
                    runId
                      ? () => void loadHistoricalEvents(runId, workflowId, attachPending)
                      : undefined
                  }
                />
              </div>
            )}

            {!effectiveLoadingHistory && filtered.length === 0 && !fetchError && (
              <div className="py-12 flex items-center justify-center">
                <p className="text-muted text-sm">
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
