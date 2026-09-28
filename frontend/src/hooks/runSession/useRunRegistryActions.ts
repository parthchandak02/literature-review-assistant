import { useCallback, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  archiveRun,
  deleteRun,
  hideCompletedRun,
  restoreCompletedRun,
  restoreRun,
  setHistoryLane,
} from "@/lib/api"
import { parseRunUrl } from "@/lib/runSessionUrl"
import type { LaneChangeOptions } from "@/components/sidebar/types"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"
import type { RunSessionActionDeps } from "@/hooks/runSession/runSessionActionDeps"

export type RunRegistryActionDeps = Pick<
  RunSessionActionDeps,
  "navigate" | "selectedRun" | "setSelectedRun" | "setActiveRunTab"
>

interface LeftRun {
  run: SelectedRun
  tab: RunTab
}

function currentRunTab(workflowId: string): RunTab {
  const parsed = parseRunUrl(window.location.pathname)
  return parsed?.workflowId === workflowId ? parsed.tab : "activity"
}

export function useRunRegistryActions({
  navigate,
  selectedRun,
  setSelectedRun,
  setActiveRunTab,
}: RunRegistryActionDeps) {
  const queryClient = useQueryClient()
  const leftRunRef = useRef<LeftRun | null>(null)

  const invalidateHistory = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["history"] })
  }, [queryClient])

  const leaveIfViewing = useCallback(
    (workflowId: string) => {
      if (!selectedRun || selectedRun.workflowId !== workflowId) return
      leftRunRef.current = { run: selectedRun, tab: currentRunTab(workflowId) }
      setSelectedRun(null)
      navigate("/", { replace: true })
    },
    [navigate, selectedRun, setSelectedRun],
  )

  const reselectLeftRun = useCallback(
    (workflowId: string) => {
      const left = leftRunRef.current
      if (!left || left.run.workflowId !== workflowId) return
      leftRunRef.current = null
      setSelectedRun(left.run)
      setActiveRunTab(left.tab)
      navigate(`/run/${workflowId}/${left.tab}`, { replace: true })
    },
    [navigate, setActiveRunTab, setSelectedRun],
  )

  const handleSidebarDelete = useCallback(
    async (workflowId: string) => {
      await deleteRun(workflowId)
      invalidateHistory()
      if (leftRunRef.current?.run.workflowId === workflowId) leftRunRef.current = null
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [invalidateHistory, navigate, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarArchive = useCallback(
    async (workflowId: string) => {
      await archiveRun(workflowId)
      invalidateHistory()
      leaveIfViewing(workflowId)
    },
    [invalidateHistory, leaveIfViewing],
  )

  const handleSidebarRestore = useCallback(
    async (workflowId: string, options?: LaneChangeOptions) => {
      await restoreRun(workflowId)
      if (options?.lane !== undefined) await setHistoryLane(workflowId, options.lane)
      invalidateHistory()
      if (options?.undo) reselectLeftRun(workflowId)
    },
    [invalidateHistory, reselectLeftRun],
  )

  const handleSidebarHideCompleted = useCallback(
    async (workflowId: string, options?: LaneChangeOptions) => {
      await hideCompletedRun(workflowId)
      invalidateHistory()
      if (options?.undo) reselectLeftRun(workflowId)
      else leaveIfViewing(workflowId)
    },
    [invalidateHistory, leaveIfViewing, reselectLeftRun],
  )

  const handleSidebarRestoreCompleted = useCallback(
    async (workflowId: string, options?: LaneChangeOptions) => {
      if (options?.lane !== undefined) await setHistoryLane(workflowId, options.lane)
      else await restoreCompletedRun(workflowId)
      invalidateHistory()
      if (options?.undo) reselectLeftRun(workflowId)
    },
    [invalidateHistory, reselectLeftRun],
  )

  return {
    handleSidebarDelete,
    handleSidebarArchive,
    handleSidebarRestore,
    handleSidebarHideCompleted,
    handleSidebarRestoreCompleted,
  }
}
