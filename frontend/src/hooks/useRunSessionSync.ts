import { useEffect, type Dispatch, type SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"
import { parseRunUrl } from "@/lib/runSessionUrl"
import {
  APIResponseError,
  attachHistory,
  clearLiveRun,
  fetchActiveRun,
  fetchArtifacts,
  fetchHistory,
  loadLiveRun,
  saveLiveRun,
} from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { queryClient } from "@/lib/queryClient"
import type { useLiveRunStream } from "@/hooks/useLiveRunStream"
import type { RunTab, SelectedRun } from "@/views/RunView"

type LiveStream = ReturnType<typeof useLiveRunStream>

export interface RunSessionSyncArgs {
  navigate: NavigateFunction
  pathname: string
  selectedRun: SelectedRun | null
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>>
  activeRunTab: RunTab
  setActiveRunTab: Dispatch<SetStateAction<RunTab>>
  setHistoryOutputs: Dispatch<SetStateAction<Record<string, string>>>
  isViewingLiveRun: boolean
  live: LiveStream
}

export function useRunSessionSync({
  navigate,
  pathname,
  selectedRun,
  setSelectedRun,
  activeRunTab,
  setActiveRunTab,
  setHistoryOutputs,
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
    liveOutputs,
    reset,
    clearLiveRunUi,
  } = live

  async function restoreRunFromUrl(workflowId: string, tab: RunTab, isAborted?: () => boolean) {
    try {
      const history = await queryClient.fetchQuery({
        queryKey: historyQueryKey(),
        queryFn: () => fetchHistory(),
      })
      if (isAborted?.()) return
      const entry = history.find((e) => e.workflow_id === workflowId)
      if (!entry) {
        navigate("/", { replace: true })
        return
      }
      if (entry.live_run_id) {
        if (isAborted?.()) return
        const now = new Date()
        reset()
        liveRunNavigatedRef.current = workflowId
        setLiveRunId(entry.live_run_id)
        setLiveTopic(entry.topic)
        setLiveStartedAt(now)
        setLiveWorkflowId(workflowId)
        saveLiveRun({
          runId: entry.live_run_id,
          topic: entry.topic,
          startedAt: now.toISOString(),
          workflowId,
        })
        setSelectedRun({
          runId: entry.live_run_id,
          workflowId,
          topic: entry.topic,
          dbPath: entry.db_path || null,
          isDone: false,
          startedAt: now,
          createdAt: entry.created_at,
        })
        setActiveRunTab(tab)
        return
      }
      const res = await attachHistory(entry)
      if (isAborted?.()) return
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
      setActiveRunTab(tab)
    } catch {
      if (!isAborted?.()) navigate("/", { replace: true })
    }
  }

  useEffect(() => {
    let aborted = false
    const stored = loadLiveRun()

    if (stored) {
      setLiveRunId(stored.runId)
      setLiveTopic(stored.topic)
      setLiveStartedAt(new Date(stored.startedAt))
      if (stored.workflowId) {
        setLiveWorkflowId(stored.workflowId)
        liveRunNavigatedRef.current = stored.workflowId
      }
    }

    const parsed = parseRunUrl(pathname)
    if (!parsed) return

    const { workflowId: urlWfId, tab: urlTab } = parsed
    setActiveRunTab(urlTab)
    if (urlWfId === "draft") {
      navigate("/", { replace: true })
      return
    }

    if (stored?.workflowId === urlWfId) {
      void (async () => {
        const active = await fetchActiveRun(urlWfId)
        if (aborted) return

        if (active && active.run_id === stored.runId) {
          setSelectedRun({
            runId: stored.runId,
            workflowId: stored.workflowId ?? null,
            topic: stored.topic,
            dbPath: null,
            isDone: false,
            startedAt: new Date(stored.startedAt),
            createdAt: stored.startedAt,
          })
          return
        }

        clearLiveRun()
        setLiveRunId(null)
        setLiveWorkflowId(null)
        setLiveTopic(null)
        setLiveStartedAt(null)
        void restoreRunFromUrl(urlWfId, urlTab, () => aborted)
      })()
    } else {
      void restoreRunFromUrl(urlWfId, urlTab, () => aborted)
    }

    return () => {
      aborted = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- mount only

  useEffect(() => {
    if (!liveOutputs || !liveRunId) return
    const wfId = liveOutputs.workflow_id as string | undefined
    if (wfId && selectedRun?.runId === liveRunId && !selectedRun.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: wfId, isDone: true } : r))
      setLiveWorkflowId(wfId)
      const stored = loadLiveRun()
      if (stored) saveLiveRun({ ...stored, workflowId: wfId })
    }
  }, [liveOutputs, liveRunId, selectedRun, setSelectedRun, setLiveWorkflowId])

  useEffect(() => {
    if (!liveWorkflowId || !liveRunId) return

    if (selectedRun?.runId === liveRunId && !selectedRun.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: liveWorkflowId } : r))
    }

    if (liveRunNavigatedRef.current !== liveWorkflowId) {
      liveRunNavigatedRef.current = liveWorkflowId
      if (!selectedRun || selectedRun.runId === liveRunId) {
        navigate(`/run/${liveWorkflowId}/${activeRunTab}`, { replace: true })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- activeRunTab and navigate are stable; intentionally excluded
  }, [liveWorkflowId, liveRunId, selectedRun?.runId, selectedRun?.workflowId])

  useEffect(() => {
    const run = selectedRun
    if (!run?.isDone || isViewingLiveRun || run.attachPending) {
      setHistoryOutputs({})
      return
    }
    if (run.historicalStatus && !isTerminalHistoricalStatus(run.historicalStatus)) {
      setHistoryOutputs({})
      return
    }
    fetchArtifacts(run.runId, { workflowIdFallback: run.workflowId })
      .then((artifacts) => setHistoryOutputs(artifacts))
      .catch((err: unknown) => {
        if (err instanceof APIResponseError && err.status === 404) {
          setHistoryOutputs({})
          return
        }
        setHistoryOutputs({})
      })
  }, [
    selectedRun,
    isViewingLiveRun,
    setHistoryOutputs,
  ])

  useEffect(() => {
    const wfId = selectedRun?.workflowId
    const isTerminalHistory = isTerminalHistoricalStatus(selectedRun?.historicalStatus)
    if (!wfId || isViewingLiveRun || isTerminalHistory) return
    const workflowId = wfId

    let consecutiveMisses = 0
    const MAX_MISSES = 10
    let switched = false

    async function checkAndSwitch() {
      if (switched) return
      const res = await fetchActiveRun(workflowId)
      if (!res) {
        consecutiveMisses++
        return
      }
      if (liveRunId === res.run_id && selectedRun?.runId === res.run_id) {
        switched = true
        return
      }
      switched = true
      consecutiveMisses = 0
      const now = new Date()
      reset()
      liveRunNavigatedRef.current = null
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
      setSelectedRun({
        runId: res.run_id,
        workflowId,
        topic: res.topic,
        dbPath: null,
        isDone: false,
        startedAt: now,
        createdAt: now.toISOString(),
      })
      setActiveRunTab("activity")
      navigate(`/run/${workflowId}/activity`, { replace: true })
    }

    void checkAndSwitch()
    const interval = setInterval(() => {
      if (switched || consecutiveMisses >= MAX_MISSES) {
        clearInterval(interval)
        return
      }
      void checkAndSwitch()
    }, 800)

    return () => clearInterval(interval)
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
  ])
}
