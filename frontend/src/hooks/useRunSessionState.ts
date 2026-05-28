import { useMemo, useState } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useLiveRunStream } from "@/hooks/useLiveRunStream"
import { useRunSessionSync } from "@/hooks/useRunSessionSync"
import { useRunSessionActions } from "@/hooks/useRunSessionActions"
import type { RunSessionContextValue } from "@/context/runSessionTypes"
import type { RunTab, SelectedRun } from "@/views/RunView"

export function useRunSessionState(): RunSessionContextValue {
  const navigate = useNavigate()
  const location = useLocation()
  const live = useLiveRunStream()

  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)
  const [activeRunTab, setActiveRunTab] = useState<RunTab>("activity")
  const [historyOutputs, setHistoryOutputs] = useState<Record<string, string>>({})
  const [submissionFocusTarget, setSubmissionFocusTarget] = useState<"reference-papers" | null>(null)
  const [submissionFocusToken, setSubmissionFocusToken] = useState(0)

  const {
    liveRunId,
    liveWorkflowId,
    events,
    status,
    costStats,
    isRunning,
    liveOutputs,
    liveRunForSidebar,
  } = live

  const dbUnlocked = useMemo(
    () =>
      selectedRun?.isDone ||
      status === "done" ||
      events.some((e) => e.type === "db_ready"),
    [selectedRun?.isDone, status, events],
  )

  const isViewingLiveRun =
    selectedRun !== null &&
    liveRunId !== null &&
    (selectedRun.runId === liveRunId ||
      (Boolean(selectedRun.workflowId) &&
        Boolean(liveWorkflowId) &&
        selectedRun.workflowId === liveWorkflowId))

  const viewEvents = isViewingLiveRun ? events : []

  useRunSessionSync({
    navigate,
    pathname: location.pathname,
    selectedRun,
    setSelectedRun,
    activeRunTab,
    setActiveRunTab,
    setHistoryOutputs,
    isViewingLiveRun,
    live,
  })

  const actions = useRunSessionActions({
    navigate,
    selectedRun,
    setSelectedRun,
    setActiveRunTab,
    setHistoryOutputs,
    setSubmissionFocusTarget,
    setSubmissionFocusToken,
    live,
  })

  return {
    selectedRun,
    setSelectedRun,
    activeRunTab,
    setActiveRunTab,
    historyOutputs,
    submissionFocusTarget,
    submissionFocusToken,
    isRunning,
    isViewingLiveRun,
    viewEvents,
    liveRunForSidebar,
    liveOutputs,
    dbUnlocked,
    status,
    costStats,
    events,
    ...actions,
  }
}
