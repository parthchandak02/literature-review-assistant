import { useEffect, type Dispatch, type SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"
import { isParkedGateStatus } from "@/lib/constants"
import { parseRunUrl } from "@/lib/runSessionUrl"
import { connectLiveRun } from "@/lib/runSession"
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

const PARKED_OUTPUT_STATUSES = new Set(["awaiting_prospero", "awaiting_review"])

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
    wasStreamingRef,
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
        connectLiveRun(
          {
            reset,
            setLiveRunId,
            setLiveTopic,
            setLiveStartedAt,
            setLiveWorkflowId,
            setSelectedRun,
            setActiveRunTab,
            liveRunNavigatedRef,
            wasStreamingRef,
          },
          {
            runId: entry.live_run_id,
            topic: entry.topic,
            workflowId,
            dbPath: entry.db_path || null,
            createdAt: entry.created_at,
            tab,
          },
        )
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

    // Parked runs (awaiting PROSPERO registration or human screening review) can sit
    // idle far longer than an active run's transient polling gaps, so give them a much
    // higher miss budget instead of giving up after ~8 seconds.
    const isParked = isParkedGateStatus(selectedRun?.historicalStatus)
    let consecutiveMisses = 0
    const MAX_MISSES = isParked ? 300 : 10
    const pollIntervalMs = isParked ? 2_500 : 800
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
        { navigatedRef: null },
      )
    }

    void checkAndSwitch()
    const interval = setInterval(() => {
      if (switched || consecutiveMisses >= MAX_MISSES) {
        clearInterval(interval)
        return
      }
      void checkAndSwitch()
    }, pollIntervalMs)

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
    wasStreamingRef,
  ])
}
