import { useMemo, type ReactNode } from "react"
import {
  RunSessionActionsContext,
  RunSessionStateContext,
} from "@/context/runSessionContext"
import { useRunSessionValue } from "@/hooks/useRunSessionValue"

export function RunSessionProvider({ children }: { children: ReactNode }) {
  const value = useRunSessionValue()

  const state = useMemo(
    () => ({
      selectedRun: value.selectedRun,
      activeRunTab: value.activeRunTab,
      historyOutputs: value.historyOutputs,
      submissionFocusTarget: value.submissionFocusTarget,
      submissionFocusToken: value.submissionFocusToken,
      isRunning: value.isRunning,
      isViewingLiveRun: value.isViewingLiveRun,
      viewEvents: value.viewEvents,
      liveRunForSidebar: value.liveRunForSidebar,
      liveOutputs: value.liveOutputs,
      dbUnlocked: value.dbUnlocked,
      status: value.status,
      costStats: value.costStats,
      events: value.events,
    }),
    [
      value.selectedRun,
      value.activeRunTab,
      value.historyOutputs,
      value.submissionFocusTarget,
      value.submissionFocusToken,
      value.isRunning,
      value.isViewingLiveRun,
      value.viewEvents,
      value.liveRunForSidebar,
      value.liveOutputs,
      value.dbUnlocked,
      value.status,
      value.costStats,
      value.events,
    ],
  )

  const actions = useMemo(
    () => ({
      setSelectedRun: value.setSelectedRun,
      setActiveRunTab: value.setActiveRunTab,
      handleStart: value.handleStart,
      handleStartWithSupplementaryCsv: value.handleStartWithSupplementaryCsv,
      handleStartWithMasterlistCsv: value.handleStartWithMasterlistCsv,
      handleCancel: value.handleCancel,
      handleNewReview: value.handleNewReview,
      handleSelectLiveRun: value.handleSelectLiveRun,
      handleSelectHistory: value.handleSelectHistory,
      handleGoHome: value.handleGoHome,
      handleSidebarResumeLauncher: value.handleSidebarResumeLauncher,
      handleTimelineResumePhase: value.handleTimelineResumePhase,
      handleSidebarDelete: value.handleSidebarDelete,
      handleSidebarArchive: value.handleSidebarArchive,
      handleSidebarRestore: value.handleSidebarRestore,
      handleSidebarHideCompleted: value.handleSidebarHideCompleted,
      handleSidebarRestoreCompleted: value.handleSidebarRestoreCompleted,
      handleTabChange: value.handleTabChange,
      handleGoToSubmissionReferencePapers: value.handleGoToSubmissionReferencePapers,
      handleSubmitProsperoAndResume: value.handleSubmitProsperoAndResume,
      handleApproveScreeningAndResume: value.handleApproveScreeningAndResume,
      openDraftRunShell: value.openDraftRunShell,
    }),
    [
      value.setSelectedRun,
      value.setActiveRunTab,
      value.handleStart,
      value.handleStartWithSupplementaryCsv,
      value.handleStartWithMasterlistCsv,
      value.handleCancel,
      value.handleNewReview,
      value.handleSelectLiveRun,
      value.handleSelectHistory,
      value.handleGoHome,
      value.handleSidebarResumeLauncher,
      value.handleTimelineResumePhase,
      value.handleSidebarDelete,
      value.handleSidebarArchive,
      value.handleSidebarRestore,
      value.handleSidebarHideCompleted,
      value.handleSidebarRestoreCompleted,
      value.handleTabChange,
      value.handleGoToSubmissionReferencePapers,
      value.handleSubmitProsperoAndResume,
      value.handleApproveScreeningAndResume,
      value.openDraftRunShell,
    ],
  )

  return (
    <RunSessionStateContext.Provider value={state}>
      <RunSessionActionsContext.Provider value={actions}>
        {children}
      </RunSessionActionsContext.Provider>
    </RunSessionStateContext.Provider>
  )
}
