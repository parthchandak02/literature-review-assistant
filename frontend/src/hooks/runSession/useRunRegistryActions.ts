import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import {
  archiveRun,
  deleteRun,
  hideCompletedRun,
  restoreCompletedRun,
  restoreRun,
} from "@/lib/api"
import type { RunSessionActionDeps } from "@/hooks/runSession/runSessionActionDeps"

export type RunRegistryActionDeps = Pick<
  RunSessionActionDeps,
  "navigate" | "selectedRun" | "setSelectedRun"
>

export function useRunRegistryActions({
  navigate,
  selectedRun,
  setSelectedRun,
}: RunRegistryActionDeps) {
  const queryClient = useQueryClient()

  const handleSidebarDelete = useCallback(
    async (workflowId: string) => {
      await deleteRun(workflowId)
      void queryClient.invalidateQueries({ queryKey: ["history"] })
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, queryClient, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarArchive = useCallback(
    async (workflowId: string) => {
      await archiveRun(workflowId)
      void queryClient.invalidateQueries({ queryKey: ["history"] })
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, queryClient, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarRestore = useCallback(async (workflowId: string) => {
    await restoreRun(workflowId)
    void queryClient.invalidateQueries({ queryKey: ["history"] })
  }, [queryClient])

  const handleSidebarHideCompleted = useCallback(
    async (workflowId: string) => {
      await hideCompletedRun(workflowId)
      void queryClient.invalidateQueries({ queryKey: ["history"] })
      if (selectedRun?.workflowId === workflowId) {
        setSelectedRun(null)
        navigate("/", { replace: true })
      }
    },
    [navigate, queryClient, selectedRun?.workflowId, setSelectedRun],
  )

  const handleSidebarRestoreCompleted = useCallback(async (workflowId: string) => {
    await restoreCompletedRun(workflowId)
    void queryClient.invalidateQueries({ queryKey: ["history"] })
  }, [queryClient])

  return {
    handleSidebarDelete,
    handleSidebarArchive,
    handleSidebarRestore,
    handleSidebarHideCompleted,
    handleSidebarRestoreCompleted,
  }
}
