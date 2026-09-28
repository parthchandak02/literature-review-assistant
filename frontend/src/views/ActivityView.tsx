import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { eventToLogEntry } from "@/lib/logLine"
import { fetchHistoricalReviewEvents } from "@/lib/api"
import { shouldShowHistoricalLoading, shouldUsePrefetchedHistorical } from "@/lib/runSelection"
import type { ReviewEvent } from "@/lib/api"
import {
  applyFailure,
  applyGateOverrides,
  buildPhaseStates,
  failureSummary,
  latestResumablePhase,
  resumeOptions,
} from "@/lib/activityPhaseState"
import { detectAwaitingProspero, detectAwaitingReview } from "@/lib/phaseProgress"
import { useDbCostDashboard } from "@/hooks/useDbCosts"
import { PhaseTimeline } from "@/components/activity/PhaseTimeline"
import { ActivityLogPanel } from "@/components/activity/ActivityLogPanel"
import { FailureBanner } from "@/components/activity/FailureBanner"
import { ResumeMenu } from "@/components/activity/ResumeMenu"
import { ResumeConfirmDialog } from "@/components/activity/ResumeConfirmDialog"

export const SERVER_UNREACHABLE_MESSAGE = "Can't reach the server."

const FAILED_STATUSES = new Set(["failed", "error"])
const RUNNING_STATUSES = new Set(["running", "streaming", "connecting"])

function fetchErrorMessage(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e)
  return msg.toLowerCase().includes("failed to fetch") ? SERVER_UNREACHABLE_MESSAGE : msg
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
}

export interface ActivityViewProps {
  events: ReviewEvent[]
  prefetchedHistoricalEvents?: ReviewEvent[] | null
  historicalEventsLoading?: boolean
  /** When true, an empty event list can fall back to persisted history. */
  allowHistoricalFallback?: boolean
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
  const [confirmResumePhase, setConfirmResumePhase] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)

  const hasPrefetchedHistorical = shouldUsePrefetchedHistorical(prefetchedHistoricalEvents)
  const isFallbackMode = allowHistoricalFallback && events.length === 0 && Boolean(runId)

  const loadHistoricalEvents = useCallback(
    async (id: string, wfId: string | null | undefined) => {
      setLoadingHistory(true)
      setFetchError(null)
      try {
        const evs = await fetchHistoricalReviewEvents(wfId, id)
        setHistoricalEvents(evs)
      } catch (e) {
        setFetchError(fetchErrorMessage(e))
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
        const evs = await fetchHistoricalReviewEvents(workflowId, runId)
        if (!cancelled) setHistoricalEvents(evs)
      } catch (e) {
        if (!cancelled) {
          setFetchError(fetchErrorMessage(e))
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
  }, [isFallbackMode, runId, workflowId, hasPrefetchedHistorical, historicalEventsLoading])

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
    normalizedHistoricalStatus === "needs_revision" ||
    status === "done"
  const isRunning = status === "streaming" || status === "connecting"
  const isFailed = status === "error" || (!isRunning && FAILED_STATUSES.has(normalizedHistoricalStatus))
  const awaitingProspero = detectAwaitingProspero({
    historicalStatus,
    status,
    events: activeEvents,
    isRunning,
  })
  const awaitingReview = detectAwaitingReview({
    historicalStatus,
    status,
    events: activeEvents,
    isRunning,
  })
  const gatedPhaseStates = useMemo(
    () =>
      applyGateOverrides(buildPhaseStates(activeEvents, completedWorkflow), {
        awaitingProspero,
        awaitingReview,
      }),
    [activeEvents, completedWorkflow, awaitingProspero, awaitingReview],
  )
  const failure = useMemo(
    () => (isFailed ? failureSummary(activeEvents, gatedPhaseStates) : null),
    [isFailed, activeEvents, gatedPhaseStates],
  )
  const phaseStates = useMemo(
    () => (failure ? applyFailure(gatedPhaseStates, failure.phase) : gatedPhaseStates),
    [failure, gatedPhaseStates],
  )
  const awaitingGateByMilestone = useMemo(
    () => ({
      ...(awaitingProspero ? { prospero: true } : {}),
      ...(awaitingReview ? { discovery: true } : {}),
    }),
    [awaitingProspero, awaitingReview],
  )
  const resumeBlockedReason = (() => {
    if (!onResumeFromPhase) return "Resume controls are not available for this run."
    if (isRunning || RUNNING_STATUSES.has(normalizedHistoricalStatus)) {
      return "Resume is unavailable while this run is in progress."
    }
    if (normalizedHistoricalStatus === "awaiting_review") {
      return "Approve screening first before resuming from later phases."
    }
    if (normalizedHistoricalStatus === "awaiting_prospero") {
      return "Complete PROSPERO registration first before resuming from later phases."
    }
    if (!resumeModeActive) return "Resume is available once the run has finished or failed."
    return null
  })()
  const canResume = resumeBlockedReason === null
  const options = useMemo(
    () => resumeOptions(phaseStates, completedWorkflow),
    [phaseStates, completedWorkflow],
  )
  const failureResumePhase = canResume ? latestResumablePhase(phaseStates, completedWorkflow) : null

  const costQuery = useDbCostDashboard(runId, { enabled: canResume && Boolean(runId) })
  const costByPhase = costQuery.data?.by_phase ?? null

  const requestResume = useCallback(
    (phase: string) => {
      if (!canResume) return
      if (!options.some((option) => option.phase === phase && option.selectable)) return
      setConfirmResumePhase(phase)
    },
    [canResume, options],
  )

  const confirmResume = useCallback(
    async (phase: string) => {
      try {
        await onResumeFromPhase?.(phase)
      } catch {
        // The resume handler reports its own errors.
      }
    },
    [onResumeFromPhase],
  )

  const showInLog = useCallback(() => {
    setSearchQuery("")
    const el = logRef.current
    if (!el) return
    el.scrollIntoView?.({ block: "start", behavior: prefersReducedMotion() ? "auto" : "smooth" })
    el.focus({ preventScroll: true })
  }, [])

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
      {failure ? (
        <FailureBanner
          phase={failure.phase}
          message={failure.message}
          resumePhase={failureResumePhase}
          onShowInLog={showInLog}
          onResume={requestResume}
        />
      ) : null}

      <div className="flex flex-col gap-3 min-h-[480px]">
        {onResumeFromPhase ? (
          <ResumeMenu
            options={options}
            blockedReason={resumeBlockedReason}
            onSelect={requestResume}
          />
        ) : null}

        <PhaseTimeline
          phaseStates={phaseStates}
          loading={effectiveLoadingHistory}
          completedWorkflow={completedWorkflow}
          showSubStatus={!completedWorkflow && !failure}
          awaitingGateByMilestone={awaitingGateByMilestone}
        />

        <div
          ref={logRef}
          tabIndex={-1}
          className="flex flex-col flex-1 min-h-0 rounded-panel focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ActivityLogPanel
            searchQuery={searchQuery}
            onSearchQueryChange={setSearchQuery}
            effectiveLoadingHistory={effectiveLoadingHistory}
            eventCountLabel={eventCountLabel}
            fetchError={fetchError}
            filteredEvents={filtered}
            runId={runId}
            workflowId={workflowId}
            onRetryHistorical={loadHistoricalEvents}
          />
        </div>
      </div>

      <ResumeConfirmDialog
        phase={canResume ? confirmResumePhase : null}
        costByPhase={costByPhase}
        costLoading={costQuery.isLoading}
        onOpenChange={(open) => {
          if (!open) setConfirmResumePhase(null)
        }}
        onConfirm={confirmResume}
      />
    </div>
  )
}
