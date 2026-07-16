import { useEffect, useMemo, useRef, useState } from "react"
import { computePhaseProgress } from "@/lib/phaseProgress"
import { computeFunnelStages } from "@/lib/funnelStages"
import { useSSEStream } from "@/hooks/useSSEStream"
import { useCostStats } from "@/hooks/useCostStats"
import { clearLiveRun, loadLiveRun, saveLiveRun } from "@/lib/api"
import type { LiveRun } from "@/components/sidebar/types"

export function useLiveRunStream() {
  const [liveRunId, setLiveRunId] = useState<string | null>(null)
  const [liveTopic, setLiveTopic] = useState<string | null>(null)
  const [liveStartedAt, setLiveStartedAt] = useState<Date | null>(null)
  const [liveWorkflowId, setLiveWorkflowId] = useState<string | null>(null)

  const liveRunNavigatedRef = useRef<string | null>(null)
  const wasStreamingRef = useRef(false)

  const { events, status, abort, reset } = useSSEStream(liveRunId, liveWorkflowId)
  const costStats = useCostStats(events)

  const isRunning = status === "streaming" || status === "connecting"

  const liveOutputs = useMemo<Record<string, unknown>>(() => {
    if (status !== "done") return {}
    const ev = [...events].reverse().find((e) => e.type === "done")
    return ev?.type === "done" ? ev.outputs : {}
  }, [status, events])

  const livePapersFound = useMemo(
    () =>
      events
        .filter((e) => e.type === "connector_result" && e.status === "success")
        .reduce((acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0), 0),
    [events],
  )

  const liveIncluded = useMemo(() => {
    const lastDecision = new Map<string, string>()
    for (const e of events) {
      if (e.type === "screening_decision") {
        lastDecision.set(e.paper_id, e.decision)
      }
    }
    return [...lastDecision.values()].filter((d) => d === "include").length
  }, [events])

  const livePhaseProgress = useMemo(() => computePhaseProgress(events), [events])
  const liveFunnelStages = useMemo(() => computeFunnelStages(events), [events])

  const liveRunForSidebar = useMemo<LiveRun | null>(
    () =>
      liveRunId
        ? {
            runId: liveRunId,
            topic: liveTopic ?? "",
            status,
            cost: costStats.total_cost,
            workflowId: liveWorkflowId,
            phaseProgress: livePhaseProgress,
            startedAt: liveStartedAt?.toISOString() ?? null,
            papersFound: livePapersFound > 0 ? livePapersFound : null,
            papersIncluded: liveIncluded > 0 ? liveIncluded : null,
            funnelStages: liveFunnelStages.length > 0 ? liveFunnelStages : undefined,
          }
        : null,
    [
      liveRunId,
      liveTopic,
      status,
      costStats.total_cost,
      liveWorkflowId,
      livePhaseProgress,
      liveStartedAt,
      livePapersFound,
      liveIncluded,
      liveFunnelStages,
    ],
  )

  function clearLiveRunUi() {
    clearLiveRun()
    reset()
    setLiveRunId(null)
    setLiveWorkflowId(null)
    setLiveTopic(null)
    setLiveStartedAt(null)
    wasStreamingRef.current = false
  }

  /* eslint-disable react-hooks/set-state-in-effect -- SSE terminal status and workflow_id_ready sync live card state */
  useEffect(() => {
    if (status === "streaming") {
      wasStreamingRef.current = true
    }
    if (status === "done" || status === "error" || status === "cancelled") {
      clearLiveRun()
      // Keep liveRunId when prefetch returns a terminal buffer without ever
      // streaming. Nulling here breaks history selection for completed runs
      // that still expose live_run_id (isViewingLiveRun would flip false).
      wasStreamingRef.current = false
    }
  }, [status])

  useEffect(() => {
    if (liveWorkflowId) return
    const ev = events.find((e) => e.type === "workflow_id_ready")
    if (!ev || ev.type !== "workflow_id_ready") return
    const wfId = ev.workflow_id
    if (wfId) {
      setLiveWorkflowId(wfId)
      const stored = loadLiveRun()
      if (stored) saveLiveRun({ ...stored, workflowId: wfId })
    }
  }, [events, liveWorkflowId])
  /* eslint-enable react-hooks/set-state-in-effect */

  return {
    liveRunId,
    setLiveRunId,
    liveTopic,
    setLiveTopic,
    liveStartedAt,
    setLiveStartedAt,
    liveWorkflowId,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
    events,
    status,
    abort,
    reset,
    costStats,
    isRunning,
    liveOutputs,
    liveRunForSidebar,
    clearLiveRunUi,
  }
}
