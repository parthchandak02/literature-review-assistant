import { useEffect } from "react"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"
import { connectLiveRun } from "@/lib/runSession"
import { createWorkflowActiveRunWatcher } from "@/hooks/workflowActiveRunWatcher"
import { loadLiveRun, saveLiveRun } from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { queryClient } from "@/lib/queryClient"
import type { RunSessionSyncArgs } from "@/hooks/useRunSessionSync"

const PARKED_OUTPUT_STATUSES = new Set(["awaiting_prospero", "awaiting_review"])

export function useRunSessionLiveEffects({
  navigate,
  selectedRun,
  setSelectedRun,
  activeRunTab,
  setActiveRunTab,
  isViewingLiveRun,
  live,
}: RunSessionSyncArgs) {
  const {
    liveRunId,
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    liveWorkflowId,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
    liveOutputs,
    reset,
    clearLiveRunUi,
  } = live

  useEffect(() => {
    if (!liveOutputs || !liveRunId) return
    const outputStatus = String(liveOutputs.status ?? "")
    if (PARKED_OUTPUT_STATUSES.has(outputStatus)) return
    const wfId = liveOutputs.workflow_id as string | undefined
    if (wfId && selectedRun?.runId === liveRunId && !selectedRun.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: wfId, isDone: true } : r))
      setLiveWorkflowId(wfId)
      const stored = loadLiveRun()
      if (stored) saveLiveRun({ ...stored, workflowId: wfId })
    }
  }, [liveOutputs, liveRunId, selectedRun, setSelectedRun, setLiveWorkflowId])

  useEffect(() => {
    const parkedStatus = String(liveOutputs?.status ?? "")
    if (!PARKED_OUTPUT_STATUSES.has(parkedStatus)) return
    const wfId = String(liveOutputs?.workflow_id ?? liveWorkflowId ?? "")
    if (!wfId || !liveRunId) return

    setSelectedRun((prev) => {
      if (!prev || prev.runId !== liveRunId) return prev
      return {
        ...prev,
        workflowId: wfId,
        dbPath: typeof liveOutputs?.db_path === "string" ? liveOutputs.db_path : prev.dbPath,
        historicalStatus: parkedStatus,
        isDone: false,
      }
    })
    clearLiveRunUi()
    void queryClient.invalidateQueries({ queryKey: historyQueryKey() })
  }, [liveOutputs, liveRunId, liveWorkflowId, setSelectedRun, clearLiveRunUi])

  useEffect(() => {
    if (!liveWorkflowId || !liveRunId) return

    if (selectedRun?.runId === liveRunId && !selectedRun.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: liveWorkflowId } : r))
    }

    if (liveRunNavigatedRef.current !== liveWorkflowId) {
      liveRunNavigatedRef.current = liveWorkflowId
      void queryClient.invalidateQueries({ queryKey: historyQueryKey() })
      if (!selectedRun || selectedRun.runId === liveRunId) {
        navigate(`/run/${liveWorkflowId}/${activeRunTab}`, { replace: true })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- activeRunTab and navigate are stable; intentionally excluded
  }, [liveWorkflowId, liveRunId, selectedRun?.runId, selectedRun?.workflowId])

  useEffect(() => {
    const wfId = selectedRun?.workflowId
    const isTerminalHistory = isTerminalHistoricalStatus(selectedRun?.historicalStatus)
    if (!wfId || isViewingLiveRun || isTerminalHistory) return
    const workflowId = wfId

    const watcher = createWorkflowActiveRunWatcher({
      workflowId,
      liveRunId,
      selectedRunId: selectedRun?.runId,
      onActiveRun: ({ run_id, topic }) => {
        connectLiveRun(
          {
            reset,
            setLiveRunId,
            setLiveTopic,
            setLiveStartedAt,
            setLiveWorkflowId,
            setSelectedRun,
            setActiveRunTab,
            navigate,
            liveRunNavigatedRef,
            wasStreamingRef,
          },
          {
            runId: run_id,
            topic,
            workflowId,
            tab: "activity",
            navigatePath: `/run/${workflowId}/activity`,
          },
          { navigatedRef: null },
        )
      },
    })

    return () => watcher.dispose()
  }, [
    selectedRun?.workflowId,
    selectedRun?.historicalStatus,
    selectedRun?.runId,
    liveRunId,
    isViewingLiveRun,
    reset,
    navigate,
    setSelectedRun,
    setActiveRunTab,
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
  ])
}
