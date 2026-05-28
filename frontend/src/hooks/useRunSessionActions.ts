import { useCallback } from "react"
import type { Dispatch, SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import { toast } from "sonner"
import { beginLiveRun, runRequestToStoredKeys } from "@/lib/runSession"
import {
  isSameRunSelection,
  isSameWorkflowSelection,
  isTerminalHistoricalStatus,
} from "@/lib/runSelection"
import {
  archiveRun,
  attachHistory,
  cancelRun,
  deleteRun,
  fetchActiveRun,
  hideCompletedRun,
  resumeRun,
  restoreCompletedRun,
  restoreRun,
  saveLiveRun,
  startRun,
  startRunWithMasterlist,
  startRunWithSupplementaryCsv,
} from "@/lib/api"
import type { HistoryEntry, RunRequest, RunResponse } from "@/lib/api"
import type { useLiveRunStream } from "@/hooks/useLiveRunStream"
import type { RunSessionActions } from "@/context/runSessionTypes"
import type { RunTab, SelectedRun } from "@/views/RunView"

type LiveStream = ReturnType<typeof useLiveRunStream>

export interface RunSessionActionsArgs {
  navigate: NavigateFunction
  selectedRun: SelectedRun | null
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>>
  setActiveRunTab: Dispatch<SetStateAction<RunTab>>
  setHistoryOutputs: Dispatch<SetStateAction<Record<string, string>>>
  setSubmissionFocusTarget: Dispatch<SetStateAction<"reference-papers" | null>>
  setSubmissionFocusToken: Dispatch<SetStateAction<number>>
  live: LiveStream
}

export function useRunSessionActions({
  navigate,
  selectedRun,
  setSelectedRun,
  setActiveRunTab,
  setHistoryOutputs,
  setSubmissionFocusTarget,
  setSubmissionFocusToken,
  live,
}: RunSessionActionsArgs): RunSessionActions {
  const {
    liveRunId,
    liveTopic,
    liveStartedAt,
    liveWorkflowId,
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
    status,
    abort,
    reset,
    clearLiveRunUi,
  } = live

  const handleResumeRun = useCallback(
    (res: RunResponse, workflowId: string) => {
      const now = new Date()
      reset()
      wasStreamingRef.current = false
      liveRunNavigatedRef.current = workflowId
      setLiveRunId(res.run_id)
      setLiveTopic(res.topic)
      setLiveStartedAt(now)
      setLiveWorkflowId(workflowId)
      saveLiveRun({
        runId: res.run_id,
        topic: res.topic,
        startedAt: now.toISOString(),
        workflowId,
      })
      const run: SelectedRun = {
        runId: res.run_id,
        workflowId,
        topic: res.topic,
        dbPath: null,
        isDone: false,
        startedAt: now,
        createdAt: now.toISOString(),
      }
      setSelectedRun(run)
      setActiveRunTab("activity")
      navigate(`/run/${workflowId}/activity`, { replace: true })
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

  const selectedRunToHistoryEntry = useCallback((): HistoryEntry | null => {
    if (!selectedRun?.workflowId || !selectedRun.dbPath) return null
    return {
      workflow_id: selectedRun.workflowId,
      topic: selectedRun.topic,
      status: selectedRun.historicalStatus ?? "stale",
      db_path: selectedRun.dbPath,
      created_at: selectedRun.createdAt ?? new Date().toISOString(),
      papers_found: selectedRun.papersFound ?? null,
      papers_included: selectedRun.papersIncluded ?? null,
      total_cost: selectedRun.historicalCost ?? null,
      live_run_id: null,
      notes: null,
    }
  }, [selectedRun])

  const beginLiveRunFromResponse = useCallback(
    (res: RunResponse) => {
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
      })
    },
    [
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

  const handleStart = useCallback(
    async (req: RunRequest) => {
      const res = await startRun(req)
      beginLiveRunFromResponse(res)
    },
    [beginLiveRunFromResponse],
  )

  const handleStartWithSupplementaryCsv = useCallback(
    async (csvFile: File, req: RunRequest) => {
      const res = await startRunWithSupplementaryCsv(
        csvFile,
        req.review_yaml,
        runRequestToStoredKeys(req),
        req.run_root,
      )
      beginLiveRunFromResponse(res)
    },
    [beginLiveRunFromResponse],
  )

  const handleStartWithMasterlistCsv = useCallback(
    async (csvFile: File, req: RunRequest) => {
      const res = await startRunWithMasterlist(
        csvFile,
        req.review_yaml,
        runRequestToStoredKeys(req),
        req.run_root,
      )
      beginLiveRunFromResponse(res)
    },
    [beginLiveRunFromResponse],
  )

  const handleCancel = useCallback(async () => {
    if (liveRunId) await cancelRun(liveRunId)
    abort()
  }, [abort, liveRunId])

  const handleNewReview = useCallback(() => {
    setSelectedRun(null)
    setHistoryOutputs({})
    navigate("/")
  }, [navigate, setHistoryOutputs, setSelectedRun])

  const handleSelectLiveRun = useCallback(() => {
    if (!liveRunId || !liveTopic) return
    setSelectedRun({
      runId: liveRunId,
      workflowId: liveWorkflowId,
      topic: liveTopic,
      dbPath: null,
      isDone: status === "done" || status === "error" || status === "cancelled",
      startedAt: liveStartedAt,
      createdAt: liveStartedAt?.toISOString() ?? null,
    })
    if (liveWorkflowId) {
      navigate(`/run/${liveWorkflowId}/activity`)
    }
  }, [
    liveRunId,
    liveTopic,
    liveWorkflowId,
    liveStartedAt,
    status,
    navigate,
    setSelectedRun,
  ])

  const handleSelectHistory = useCallback(
    async (entry: HistoryEntry) => {
      const focusSelectedWorkflow = () => {
        setActiveRunTab("activity")
        navigate(`/run/${entry.workflow_id}/activity`, { replace: true })
      }

      if (isSameWorkflowSelection(selectedRun?.workflowId, entry.workflow_id)) {
        focusSelectedWorkflow()
        return
      }

      const terminalHistorical =
        isTerminalHistoricalStatus(entry.status) && !entry.live_run_id

      if (terminalHistorical) {
        clearLiveRunUi()
        const isCompleted = isTerminalHistoricalStatus(entry.status)
        setSelectedRun({
          runId: entry.workflow_id,
          workflowId: entry.workflow_id,
          topic: entry.topic,
          dbPath: entry.db_path,
          isDone: isCompleted,
          historicalStatus: entry.status,
          startedAt: null,
          createdAt: entry.created_at,
          papersFound: entry.papers_found ?? null,
          papersIncluded: entry.papers_included ?? null,
          historicalCost: entry.total_cost ?? null,
          attachPending: true,
        })
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
      if (active) {
        if (
          isSameRunSelection(
            liveRunId,
            selectedRun?.runId,
            selectedRun?.workflowId,
            active.run_id,
            entry.workflow_id,
          )
        ) {
          focusSelectedWorkflow()
          return
        }
        const now = new Date()
        if (liveRunId !== active.run_id) {
          reset()
        }
        liveRunNavigatedRef.current = entry.workflow_id
        setLiveRunId(active.run_id)
        setLiveTopic(active.topic || entry.topic)
        setLiveStartedAt(now)
        setLiveWorkflowId(entry.workflow_id)
        saveLiveRun({
          runId: active.run_id,
          topic: active.topic || entry.topic,
          startedAt: now.toISOString(),
          workflowId: entry.workflow_id,
        })
        setSelectedRun({
          runId: active.run_id,
          workflowId: entry.workflow_id,
          topic: active.topic || entry.topic,
          dbPath: entry.db_path || null,
          isDone: false,
          startedAt: now,
          createdAt: entry.created_at,
        })
        focusSelectedWorkflow()
        return
      }

      if (entry.live_run_id) {
        if (
          isSameRunSelection(
            liveRunId,
            selectedRun?.runId,
            selectedRun?.workflowId,
            entry.live_run_id,
            entry.workflow_id,
          )
        ) {
          focusSelectedWorkflow()
          return
        }
        const now = new Date()
        if (liveRunId !== entry.live_run_id) {
          reset()
        }
        liveRunNavigatedRef.current = entry.workflow_id
        setLiveRunId(entry.live_run_id)
        setLiveTopic(entry.topic)
        setLiveStartedAt(now)
        setLiveWorkflowId(entry.workflow_id)
        saveLiveRun({
          runId: entry.live_run_id,
          topic: entry.topic,
          startedAt: now.toISOString(),
          workflowId: entry.workflow_id,
        })
        setSelectedRun({
          runId: entry.live_run_id,
          workflowId: entry.workflow_id,
          topic: entry.topic,
          dbPath: entry.db_path || null,
          isDone: false,
          startedAt: now,
          createdAt: entry.created_at,
        })
        focusSelectedWorkflow()
        return
      }

      const res = await attachHistory(entry)
      clearLiveRunUi()
      const isCompleted = isTerminalHistoricalStatus(entry.status)
      setSelectedRun({
        runId: res.run_id,
        workflowId: entry.workflow_id,
        topic: entry.topic,
        dbPath: entry.db_path,
        isDone: isCompleted,
        historicalStatus: entry.status,
        startedAt: null,
        createdAt: entry.created_at,
        papersFound: entry.papers_found ?? null,
        papersIncluded: entry.papers_included ?? null,
        historicalCost: entry.total_cost ?? null,
      })
      navigate(`/run/${entry.workflow_id}/activity`)
    },
    [
      clearLiveRunUi,
      liveRunId,
      liveRunNavigatedRef,
      navigate,
      reset,
      selectedRun?.runId,
      selectedRun?.workflowId,
      setActiveRunTab,
      setLiveRunId,
      setLiveStartedAt,
      setLiveTopic,
      setLiveWorkflowId,
      setSelectedRun,
    ],
  )

  const handleGoHome = useCallback(() => {
    setSelectedRun(null)
    navigate("/")
  }, [navigate, setSelectedRun])

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

  const handleSidebarDelete = useCallback(
    async (workflowId: string) => {
      await deleteRun(workflowId)
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarArchive = useCallback(
    async (workflowId: string) => {
      await archiveRun(workflowId)
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarRestore = useCallback(async (workflowId: string) => {
    await restoreRun(workflowId)
  }, [])

  const handleSidebarHideCompleted = useCallback(
    async (workflowId: string) => {
      await hideCompletedRun(workflowId)
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarRestoreCompleted = useCallback(async (workflowId: string) => {
    await restoreCompletedRun(workflowId)
  }, [])

  const handleTabChange = useCallback(
    (tab: RunTab) => {
      setActiveRunTab(tab)
      if (tab !== "results") setSubmissionFocusTarget(null)
      if (selectedRun?.workflowId) {
        navigate(`/run/${selectedRun.workflowId}/${tab}`, { replace: true })
      }
    },
    [navigate, selectedRun, setActiveRunTab, setSubmissionFocusTarget],
  )

  const handleGoToSubmissionReferencePapers = useCallback(() => {
    setSubmissionFocusTarget("reference-papers")
    setSubmissionFocusToken((v) => v + 1)
    setActiveRunTab("results")
    if (selectedRun?.workflowId) {
      navigate(`/run/${selectedRun.workflowId}/results`, { replace: true })
    }
  }, [navigate, selectedRun, setActiveRunTab, setSubmissionFocusTarget, setSubmissionFocusToken])

  const openDraftRunShell = useCallback(
    (topic: string) => {
      const now = new Date()
      setSelectedRun({
        runId: "draft",
        workflowId: "draft",
        topic,
        dbPath: null,
        isDone: false,
        startedAt: now,
        createdAt: now.toISOString(),
      })
      setActiveRunTab("config")
      navigate("/run/draft/config", { replace: true })
    },
    [navigate, setActiveRunTab, setSelectedRun],
  )

  return {
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
    handleCancel,
    handleNewReview,
    handleSelectLiveRun,
    handleSelectHistory,
    handleGoHome,
    handleSidebarResumeLauncher,
    handleTimelineResumePhase,
    handleSidebarDelete,
    handleSidebarArchive,
    handleSidebarRestore,
    handleSidebarHideCompleted,
    handleSidebarRestoreCompleted,
    handleTabChange,
    handleGoToSubmissionReferencePapers,
    openDraftRunShell,
  }
}
