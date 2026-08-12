import { useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  approveScreening,
  fetchActiveRun,
  fetchHistory,
  regenerateProsperoDocs,
  resumeRun,
  submitProsperoRegistration,
} from "@/lib/api"
import type { ProsperoRegistration, RunResponse, ScreeningOverride } from "@/lib/api"
import type { SelectedRun } from "@/context/runSessionTypes"
import { selectedRunToHistoryEntry } from "@/lib/runSessionSelection"
import { runConfigQueryKey } from "@/hooks/useRunConfig"

export interface RunSessionGateActionDeps {
  selectedRun: SelectedRun | null
  handleResumeRun: (res: RunResponse, workflowId: string) => void
}

export function useRunGateActions(deps: RunSessionGateActionDeps) {
  const { selectedRun, handleResumeRun } = deps
  const queryClient = useQueryClient()

  const resolveHistoryEntry = useCallback(() => selectedRunToHistoryEntry(selectedRun), [selectedRun])

  const invalidateRegistrationQueries = useCallback(() => {
    if (selectedRun?.workflowId) {
      void queryClient.invalidateQueries({ queryKey: runConfigQueryKey(selectedRun.workflowId) })
    }
    void queryClient.invalidateQueries({ queryKey: ["history"] })
  }, [queryClient, selectedRun])

  const handleSubmitProsperoAndResume = useCallback(
    async (runId: string, registration: ProsperoRegistration) => {
      await submitProsperoRegistration(runId, registration, { resume: true })

      let entry = resolveHistoryEntry()
      if (!entry && selectedRun?.workflowId) {
        const history = await fetchHistory()
        const match = history.find((item) => item.workflow_id === selectedRun.workflowId)
        if (match) {
          entry = {
            ...match,
            db_path: match.db_path || selectedRun.dbPath || "",
          }
        }
      }

      if (entry?.db_path) {
        try {
          const res = await resumeRun(entry)
          handleResumeRun(res, entry.workflow_id)
          invalidateRegistrationQueries()
          toast.success("Research started")
          return
        } catch (error) {
          const msg = error instanceof Error ? error.message : String(error)
          if (!msg.includes("409")) {
            toast.error(msg || "Failed to resume workflow after PROSPERO submission")
            throw error
          }
        }
      }

      const workflowId = entry?.workflow_id ?? selectedRun?.workflowId
      if (workflowId) {
        const active = await fetchActiveRun(workflowId).catch(() => null)
        if (active) {
          handleResumeRun(active, workflowId)
          invalidateRegistrationQueries()
          toast.success("Research started")
          return
        }
      }

      invalidateRegistrationQueries()
      toast.success("PROSPERO registration submitted")
    },
    [handleResumeRun, invalidateRegistrationQueries, selectedRun, resolveHistoryEntry],
  )

  const handleUpdateProsperoRegistration = useCallback(
    async (runId: string, registration: ProsperoRegistration) => {
      await submitProsperoRegistration(runId, registration, { resume: false })
      invalidateRegistrationQueries()
      toast.success("PROSPERO registration saved")
    },
    [invalidateRegistrationQueries],
  )

  const handleRegenerateProsperoDocs = useCallback(
    async (runId: string) => {
      await regenerateProsperoDocs(runId)
      invalidateRegistrationQueries()
      toast.success("PROSPERO drafts regenerated")
    },
    [invalidateRegistrationQueries],
  )

  const handleApproveScreeningAndResume = useCallback(
    async (runId: string, overrides?: ScreeningOverride[]) => {
      await approveScreening(runId, overrides)

      let entry = resolveHistoryEntry()
      if (!entry && selectedRun?.workflowId) {
        const history = await fetchHistory()
        const match = history.find((item) => item.workflow_id === selectedRun.workflowId)
        if (match) {
          entry = {
            ...match,
            db_path: match.db_path || selectedRun.dbPath || "",
          }
        }
      }

      if (entry?.db_path) {
        try {
          const res = await resumeRun(entry)
          handleResumeRun(res, entry.workflow_id)
          void queryClient.invalidateQueries({ queryKey: ["history"] })
          toast.success("Screening approved, resuming research")
          return
        } catch (error) {
          const msg = error instanceof Error ? error.message : String(error)
          if (!msg.includes("409")) {
            toast.error(msg || "Failed to resume workflow after screening approval")
            throw error
          }
        }
      }

      if (entry?.workflow_id) {
        const active = await fetchActiveRun(entry.workflow_id).catch(() => null)
        if (active) {
          handleResumeRun(active, entry.workflow_id)
          void queryClient.invalidateQueries({ queryKey: ["history"] })
          toast.success("Screening approved, resuming research")
          return
        }
      }

      void queryClient.invalidateQueries({ queryKey: ["history"] })
      toast.success("Screening approved")
    },
    [handleResumeRun, queryClient, selectedRun, resolveHistoryEntry],
  )

  return {
    handleSubmitProsperoAndResume,
    handleUpdateProsperoRegistration,
    handleRegenerateProsperoDocs,
    handleApproveScreeningAndResume,
  }
}
