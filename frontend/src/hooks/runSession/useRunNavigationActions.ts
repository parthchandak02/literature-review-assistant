import { useCallback } from "react"
import type { RunTab } from "@/context/runSessionTypes"
import type { RunSessionActionDeps } from "@/hooks/runSession/runSessionActionDeps"

export function useRunNavigationActions({
  navigate,
  selectedRun,
  setSelectedRun,
  setActiveRunTab,
  setHistoryOutputs,
  setSubmissionFocusTarget,
  setSubmissionFocusToken,
  live,
}: RunSessionActionDeps) {
  const { liveRunId, liveTopic, liveWorkflowId, liveStartedAt, status } = live

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

  const handleGoHome = useCallback(() => {
    setSelectedRun(null)
    navigate("/")
  }, [navigate, setSelectedRun])

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
    handleTabChange,
    handleGoHome,
    handleNewReview,
    handleSelectLiveRun,
    handleGoToSubmissionReferencePapers,
    openDraftRunShell,
  }
}
