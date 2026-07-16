/**
 * Run session types and action contract.
 */
import type { Dispatch, SetStateAction } from "react"
import type { CostStats } from "@/hooks/useCostStats"
import type { HistoryEntry, RunRequest, ReviewEvent } from "@/lib/api"
import type { LiveRun } from "@/components/sidebar/types"

export type RunTab = "activity" | "results" | "database" | "cost" | "config" | "review-screening"

/** A run that is currently being viewed (live or historical). */
export interface SelectedRun {
  /** Backend run_id for /api/db/{runId}/... and /api/run/{runId}/... calls. */
  runId: string
  /** Stable workflow UUID -- available after run completes or for historical runs. */
  workflowId: string | null
  topic: string
  dbPath: string | null
  isDone: boolean
  startedAt: Date | null
  /** Populated from HistoryEntry for historical runs; null for live runs. */
  createdAt?: string | null
  papersFound?: number | null
  papersIncluded?: number | null
  historicalCost?: number | null
  /** Raw backend status string for historical runs (e.g. "running", "failed", "completed"). */
  historicalStatus?: string | null
  /** True while POST /history/attach is in flight for a completed workflow. */
  attachPending?: boolean
}
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
