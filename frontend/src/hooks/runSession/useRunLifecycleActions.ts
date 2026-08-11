import { useCallback } from "react"
import { toast } from "sonner"
import { connectLiveRun, runRequestToStoredKeys } from "@/lib/runSession"
import { isSameWorkflowSelection, isTerminalHistoricalStatus } from "@/lib/runSelection"
import {
  resolveHistorySelectTransition,
  selectedRunFromHistoryEntry,
} from "@/lib/runSessionSelection"
import { isProsperoPendingStatus } from "@/lib/constants"
import {
  attachHistory,
  cancelRun,
  fetchActiveRun,
  resumeRun,
  startRun,
  startRunWithMasterlist,
  startRunWithSupplementaryCsv,
} from "@/lib/api"
import type { HistoryEntry, RunRequest } from "@/lib/api"
import type { RunTab } from "@/context/runSessionTypes"
import type { RunSessionLifecycleActionDeps } from "@/hooks/runSession/runSessionActionDeps"
import type { RunSessionLiveConnectHandles } from "@/hooks/runSession/useRunLiveConnect"

export function useRunLifecycleActions(
  deps: RunSessionLifecycleActionDeps,
  liveConnect: RunSessionLiveConnectHandles,
) {
  const { navigate, selectedRun, setSelectedRun, setActiveRunTab, live } = deps
  const {
    liveRunId,
    abort,
    clearLiveRunUi,
    reset,
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
  } = live

  const { beginLiveRunFromResponse, handleResumeRun, selectedRunToHistoryEntry } = liveConnect

  const handleStart = useCallback(
    async (req: RunRequest, options?: { tab?: RunTab }) => {
      const res = await startRun(req)
      beginLiveRunFromResponse(res, options)
    },
    [beginLiveRunFromResponse],
  )

  const handleStartWithSupplementaryCsv = useCallback(
    async (csvFile: File, req: RunRequest, options?: { tab?: RunTab }) => {
      const res = await startRunWithSupplementaryCsv(
        csvFile,
        req.review_yaml,
        runRequestToStoredKeys(req),
        req.run_root,
      )
      beginLiveRunFromResponse(res, options)
    },
    [beginLiveRunFromResponse],
  )

  const handleStartWithMasterlistCsv = useCallback(
    async (csvFile: File, req: RunRequest, options?: { tab?: RunTab }) => {
      const res = await startRunWithMasterlist(
        csvFile,
        req.review_yaml,
        runRequestToStoredKeys(req),
        req.run_root,
      )
      beginLiveRunFromResponse(res, options)
    },
    [beginLiveRunFromResponse],
  )

  const handleCancel = useCallback(async () => {
    if (liveRunId) await cancelRun(liveRunId)
    abort()
  }, [abort, liveRunId])

  const handleSelectHistory = useCallback(
    async (entry: HistoryEntry) => {
      const focusSelectedWorkflow = () => {
        const tab = isProsperoPendingStatus(entry.status) ? "config" : "activity"
        setActiveRunTab(tab)
        navigate(`/run/${entry.workflow_id}/${tab}`, { replace: true })
      }

      if (isSameWorkflowSelection(selectedRun?.workflowId, entry.workflow_id)) {
        focusSelectedWorkflow()
        return
      }

      const terminalHistorical =
        isTerminalHistoricalStatus(entry.status) && !entry.live_run_id
      if (terminalHistorical) {
        clearLiveRunUi()
        setSelectedRun(
          selectedRunFromHistoryEntry(entry, {
            runId: entry.workflow_id,
            attachPending: true,
          }),
        )
        focusSelectedWorkflow()
        try {
          const res = await attachHistory(entry)
          setSelectedRun((current) => {
            if (current?.workflowId !== entry.workflow_id) return current
            return {
              ...current,
              runId: res.run_id,
              attachPending: false,
            }
          })
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          toast.error(`Could not open run: ${msg}`)
        }
        return
      }

      const active = await fetchActiveRun(entry.workflow_id).catch(() => null)
      const transition = resolveHistorySelectTransition(
        entry,
        { selectedRun, liveRunId },
        active,
      )

      switch (transition.kind) {
        case "focus_same_run":
          focusSelectedWorkflow()
          return

        case "connect_live": {
          const tab = isProsperoPendingStatus(entry.status) ? "config" : "activity"
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
              runId: transition.runId,
              topic: transition.topic,
              workflowId: entry.workflow_id,
              dbPath: entry.db_path || null,
              createdAt: entry.created_at,
              tab,
              navigatePath: `/run/${entry.workflow_id}/${tab}`,
            },
            {
              skipResetIfSameRun: true,
              currentLiveRunId: liveRunId,
            },
          )
          return
        }

        case "attach_historical": {
          const res = await attachHistory(entry)
          clearLiveRunUi()
          setSelectedRun(
            selectedRunFromHistoryEntry(entry, {
              runId: res.run_id,
            }),
          )
          const tab = isProsperoPendingStatus(entry.status) ? "config" : "activity"
          setActiveRunTab(tab)
          navigate(`/run/${entry.workflow_id}/${tab}`)
          return
        }
      }
    },
    [
      clearLiveRunUi,
      liveRunId,
      liveRunNavigatedRef,
      navigate,
      reset,
      selectedRun,
      setActiveRunTab,
      setLiveRunId,
      setLiveStartedAt,
      setLiveTopic,
      setLiveWorkflowId,
      setSelectedRun,
      wasStreamingRef,
    ],
  )

  const executeTimelineResume = useCallback(
    async (fromPhase?: string | null) => {
      const entry = selectedRunToHistoryEntry()
      if (!entry) return
      try {
        const res = await resumeRun(entry, fromPhase)
        handleResumeRun(res, entry.workflow_id)
        if (fromPhase) {
          toast.success("Resumed from selected phase")
        } else {
          toast.success("Resumed from last checkpoint")
        }
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        if (msg.includes("400")) {
          toast.error("Invalid resume phase. Try a different phase.")
        } else if (msg.includes("409")) {
          toast.error("Workflow already running. Open live run or stop it before resuming.")
        } else {
          toast.error(msg || "Failed to resume run")
        }
        throw error
      }
    },
    [handleResumeRun, selectedRunToHistoryEntry],
  )

  const handleSidebarResumeLauncher = useCallback(
    async (entry: HistoryEntry) => {
      try {
        const res = await resumeRun(entry)
        handleResumeRun(res, entry.workflow_id)
        toast.success("Resumed from last checkpoint")
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error)
        if (msg.includes("400")) {
          toast.error("Invalid resume phase. Try a different phase.")
        } else if (msg.includes("409")) {
          toast.error("Workflow already running. Open live run or stop it before resuming.")
        } else {
          toast.error(msg || "Failed to resume run")
        }
        throw error
      }
    },
    [handleResumeRun],
  )

  const handleTimelineResumePhase = useCallback(
    async (phase: string) => {
      await executeTimelineResume(phase)
    },
    [executeTimelineResume],
  )

  return {
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
    handleCancel,
    handleSelectHistory,
    handleSidebarResumeLauncher,
    handleTimelineResumePhase,
  }
}
