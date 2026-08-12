import { useEffect } from "react"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"
import { parseRunUrl } from "@/lib/runSessionUrl"
import { connectLiveRun } from "@/lib/runSession"
import { selectedRunFromHistoryEntry } from "@/lib/runSessionSelection"
import {
  attachHistory,
  clearLiveRun,
  fetchActiveRun,
  fetchHistory,
  loadLiveRun,
} from "@/lib/api"
import { historyQueryKey } from "@/hooks/useHistory"
import { queryClient } from "@/lib/queryClient"
import type { RunSessionSyncArgs } from "@/hooks/useRunSessionSync"
import type { RunTab } from "@/views/RunView"

export function useRunSessionUrlSync({
  navigate,
  pathname,
  setSelectedRun,
  setActiveRunTab,
  live,
}: RunSessionSyncArgs) {
  const {
    setLiveRunId,
    setLiveTopic,
    setLiveStartedAt,
    setLiveWorkflowId,
    liveRunNavigatedRef,
    wasStreamingRef,
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
      if (isTerminalHistoricalStatus(entry.status) && !entry.live_run_id) {
        if (isAborted?.()) return
        clearLiveRunUi()
        setSelectedRun(
          selectedRunFromHistoryEntry(entry, {
            runId: entry.workflow_id,
          }),
        )
        setActiveRunTab(tab)
        return
      }
      const res = await attachHistory(entry)
      if (isAborted?.()) return
      clearLiveRunUi()
      setSelectedRun(
        selectedRunFromHistoryEntry(entry, {
          runId: res.run_id,
        }),
      )
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
}
