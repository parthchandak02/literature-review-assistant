import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { eventToLogEntry } from "@/lib/logLine"
import { fetchHistoricalReviewEvents } from "@/lib/api"
import { shouldShowHistoricalLoading, shouldUsePrefetchedHistorical } from "@/lib/runSelection"
import { PHASE_MILESTONES } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { buildPhaseStates, applyGateOverrides, isPhaseResumeSelectable } from "@/lib/activityPhaseState"
import { detectAwaitingProspero, detectAwaitingReview } from "@/lib/phaseProgress"
import { PhaseTimeline } from "@/components/activity/PhaseTimeline"
import { ActivityLogPanel } from "@/components/activity/ActivityLogPanel"

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
  const [armedResumePhase, setArmedResumePhase] = useState<string | null>(null)
  const [isSubmittingResume, setIsSubmittingResume] = useState(false)

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
        const evs = await fetchHistoricalReviewEvents(workflowId, runId)
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
    status === "done"
  const isRunning = status === "streaming" || status === "connecting"
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
  const phaseStates = useMemo(
    () =>
      applyGateOverrides(buildPhaseStates(activeEvents, completedWorkflow), {
        awaitingProspero,
        awaitingReview,
      }),
    [activeEvents, completedWorkflow, awaitingProspero, awaitingReview],
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
    if (normalizedHistoricalStatus === "awaiting_prospero") {
      return "Complete PROSPERO registration first before resuming from later phases."
    }
    return null
  })()
  const canResumeEligibility = resumeBlockedReason === null
  const canResumeFromTimeline = resumeModeActive && canResumeEligibility
  const checkPhaseResumeSelectable = useCallback(
    (phase: string) => isPhaseResumeSelectable(phase, phaseStates, completedWorkflow),
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
    }, 8000)
    return () => clearTimeout(timer)
  }, [armedResumePhase])

  useEffect(() => {
    if (resumeModeActive) return
    setArmedResumePhase(null)
  }, [resumeModeActive])

  async function handlePhaseResumeTap(phase: string) {
    if (!canResumeFromTimeline || isSubmittingResume) return
    if (!checkPhaseResumeSelectable(phase)) return
    if (armedResumePhase !== phase) {
      setArmedResumePhase(phase)
      return
    }
    setIsSubmittingResume(true)
    try {
      await onResumeFromPhase?.(phase)
      setArmedResumePhase(null)
    } catch {
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
        <PhaseTimeline
          phaseStates={phaseStates}
          loading={effectiveLoadingHistory}
          completedWorkflow={completedWorkflow}
          canResumeFromTimeline={canResumeFromTimeline}
          isPhaseResumeSelectable={checkPhaseResumeSelectable}
          armedResumePhase={armedResumePhase}
          armedMilestoneStartIdx={armedMilestoneStartIdx}
          awaitingGateByMilestone={awaitingGateByMilestone}
          onResumeTap={handlePhaseResumeTap}
        />

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
  )
}
