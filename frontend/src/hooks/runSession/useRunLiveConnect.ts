import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { beginLiveRun, connectLiveRun } from "@/lib/runSession"
import type { RunResponse } from "@/lib/api"
import type { RunTab } from "@/context/runSessionTypes"
import type { RunSessionLiveConnectDeps } from "@/hooks/runSession/runSessionActionDeps"
import { selectedRunToHistoryEntry as mapSelectedRunToHistoryEntry } from "@/lib/runSessionSelection"

export type RunSessionLiveConnectHandles = {
  handleResumeRun: (res: RunResponse, workflowId: string) => void
  beginLiveRunFromResponse: (res: RunResponse, options?: { tab?: RunTab }) => void
  selectedRunToHistoryEntry: () => ReturnType<typeof mapSelectedRunToHistoryEntry>
}

export function useRunLiveConnect(deps: RunSessionLiveConnectDeps): RunSessionLiveConnectHandles {
  const { navigate, selectedRun, setSelectedRun, setActiveRunTab, live } = deps
  const queryClient = useQueryClient()
  const {
    reset,
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
  } = live

  const handleResumeRun = useCallback(
    (res: RunResponse, workflowId: string) => {
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
          runId: res.run_id,
          topic: res.topic,
          workflowId,
          tab: "activity",
          navigatePath: `/run/${workflowId}/activity`,
        },
      )
    },
    [
      navigate,
      reset,
      setActiveRunTab,
      setLiveRunId,
      setLiveStartedAt,
      setLiveTopic,
      setLiveWorkflowId,
      setSelectedRun,
      liveRunNavigatedRef,
      wasStreamingRef,
    ],
  )

  const selectedRunToHistoryEntry = useCallback(
    () => mapSelectedRunToHistoryEntry(selectedRun),
    [selectedRun],
  )

  const beginLiveRunFromResponse = useCallback(
    (res: RunResponse, options?: { tab?: RunTab }) => {
      beginLiveRun({
        res,
        reset,
        setLiveRunId,
        setLiveTopic,
        setLiveStartedAt,
        setLiveWorkflowId,
        setSelectedRun,
        setActiveRunTab,
        liveRunNavigatedRef,
        wasStreamingRef,
        tab: options?.tab ?? "activity",
      })
      void queryClient.invalidateQueries({ queryKey: ["history"] })
    },
    [
      queryClient,
      reset,
      setActiveRunTab,
      setLiveRunId,
      setLiveStartedAt,
      setLiveTopic,
      setLiveWorkflowId,
      setSelectedRun,
      liveRunNavigatedRef,
      wasStreamingRef,
    ],
  )

  return {
    handleResumeRun,
    beginLiveRunFromResponse,
    selectedRunToHistoryEntry,
  }
}
