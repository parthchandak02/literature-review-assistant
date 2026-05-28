/**
 * Run session types and action contract.
 */
import type { Dispatch, SetStateAction } from "react"
import type { CostStats } from "@/hooks/useCostStats"
import type { HistoryEntry, RunRequest, ReviewEvent } from "@/lib/api"
import type { LiveRun } from "@/components/sidebar/types"
import type { SelectedRun, RunTab } from "@/views/RunView"

export type { SelectedRun, RunTab } from "@/views/RunView"
export {
  beginLiveRun,
  resumeErrorMessage,
  runRequestToStoredKeys,
  type BeginLiveRunArgs,
} from "@/lib/runSession"

export type RunSessionStreamStatus =
  | "idle"
  | "connecting"
  | "streaming"
  | "done"
  | "error"
  | "cancelled"

export interface RunSessionViewState {
  selectedRun: SelectedRun | null
  activeRunTab: RunTab
  historyOutputs: Record<string, string>
  submissionFocusTarget: "reference-papers" | null
  submissionFocusToken: number
  isRunning: boolean
  isViewingLiveRun: boolean
  viewEvents: ReviewEvent[]
  liveRunForSidebar: LiveRun | null
  liveOutputs: Record<string, unknown>
  dbUnlocked: boolean
  status: RunSessionStreamStatus
  costStats: CostStats
  events: ReviewEvent[]
}

export interface RunSessionActions {
  handleStart: (req: RunRequest) => Promise<void>
  handleStartWithSupplementaryCsv: (csvFile: File, req: RunRequest) => Promise<void>
  handleStartWithMasterlistCsv: (csvFile: File, req: RunRequest) => Promise<void>
  handleCancel: () => Promise<void>
  handleNewReview: () => void
  handleSelectLiveRun: () => void
  handleSelectHistory: (entry: HistoryEntry) => Promise<void>
  handleGoHome: () => void
  handleSidebarResumeLauncher: (entry: HistoryEntry) => Promise<void>
  handleTimelineResumePhase: (phase: string) => Promise<void>
  handleSidebarDelete: (workflowId: string) => Promise<void>
  handleSidebarArchive: (workflowId: string) => Promise<void>
  handleSidebarRestore: (workflowId: string) => Promise<void>
  handleSidebarHideCompleted: (workflowId: string) => Promise<void>
  handleSidebarRestoreCompleted: (workflowId: string) => Promise<void>
  handleTabChange: (tab: RunTab) => void
  handleGoToSubmissionReferencePapers: () => void
  openDraftRunShell: (topic: string) => void
}

export interface RunSessionContextValue extends RunSessionViewState, RunSessionActions {
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>>
  setActiveRunTab: Dispatch<SetStateAction<RunTab>>
}
