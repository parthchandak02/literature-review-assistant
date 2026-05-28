/**
 * Run session types and action contract (App owns state wiring).
 */
export type { SelectedRun, RunTab } from "@/views/RunView"
export {
  beginLiveRun,
  resumeErrorMessage,
  runRequestToStoredKeys,
  type BeginLiveRunArgs,
} from "@/lib/runSession"

export interface RunSessionActions {
  selectHistory: (run: import("@/views/RunView").SelectedRun) => void
  start: (req: import("@/lib/api/types").RunRequest) => Promise<void>
  resume: (entry: import("@/lib/api/types").HistoryEntry, fromPhase?: string | null) => Promise<void>
  cancel: () => Promise<void>
  setTab: (tab: import("@/views/RunView").RunTab) => void
}

export interface RunSession {
  selectedRun: import("@/views/RunView").SelectedRun | null
  tab: import("@/views/RunView").RunTab
  actions: RunSessionActions
}
