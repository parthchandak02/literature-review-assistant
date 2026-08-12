import { useEffect } from "react"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"
import { APIResponseError, fetchArtifacts } from "@/lib/api"
import type { RunSessionSyncArgs } from "@/hooks/useRunSessionSync"

export function useRunSessionArtifactsSync({
  selectedRun,
  isViewingLiveRun,
  setHistoryOutputs,
}: RunSessionSyncArgs) {
  useEffect(() => {
    const run = selectedRun
    if (!run?.isDone || isViewingLiveRun) {
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
}
