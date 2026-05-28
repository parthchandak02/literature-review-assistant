import type { HistoryEntry } from "@/lib/api"
import type { RunStatus } from "@/lib/constants"
import { resolveRunStatus } from "@/lib/constants"
import type { LiveRun } from "@/components/sidebar/types"

export interface InProgressRowModel {
  entry: HistoryEntry
  statusKey: RunStatus
  isLiveRow: boolean
  isReconnectingRow: boolean
  isSelected: boolean
  isOpening: boolean
  canOpen: boolean
  rowIsRunning: boolean
  isResumable: boolean
  isCompletedLaneEligible: boolean
  actionPadClass: string
  isResuming: boolean
  progressValue: number | undefined
  papersFound: number | null | undefined
  papersIncluded: number | null | undefined
  funnelStages: LiveRun["funnelStages"]
  cost: number | null | undefined
}

export function buildInProgressRowModel(
  entry: HistoryEntry,
  liveRun: LiveRun | null,
  selectedWorkflowId: string | null,
  openingId: string | null,
  resumingId: string | null,
  options: {
    onResume?: (entry: HistoryEntry) => Promise<void>
    onArchive?: (workflowId: string) => Promise<void>
    onHideCompleted?: (workflowId: string) => Promise<void>
  },
): InProgressRowModel {
  const isLiveRow = Boolean(
    liveRun &&
      ((entry.live_run_id && entry.live_run_id === liveRun.runId) ||
        (liveRun.workflowId && entry.workflow_id === liveRun.workflowId)),
  )
  const statusKey = isLiveRow && liveRun ? liveRun.status : resolveRunStatus(entry.status)
  const isReconnectingRow =
    !isLiveRow &&
    !entry.live_run_id &&
    (statusKey === "streaming" || statusKey === "connecting")
  const rowIsRunning = isLiveRow
    ? statusKey === "streaming" || statusKey === "connecting"
    : Boolean(entry.live_run_id) || isReconnectingRow
  const isCompletedLaneEligible =
    !rowIsRunning && !entry.is_completed_hidden && options.onHideCompleted !== undefined
  const isResumable =
    options.onResume !== undefined &&
    !entry.live_run_id &&
    !["streaming", "connecting"].includes(statusKey) &&
    ["cancelled", "error", "stale"].includes(statusKey)
  const actionPadClass =
    isResumable && (options.onArchive || isCompletedLaneEligible)
      ? "pr-24"
      : options.onArchive || isResumable || isCompletedLaneEligible
        ? "pr-14"
        : ""

  const progressValue =
    isLiveRow && liveRun
      ? (liveRun.phaseProgress?.value ?? (rowIsRunning ? -1 : undefined))
      : statusKey === "done"
        ? 1
        : entry.live_run_id || isReconnectingRow
          ? -1
          : undefined

  return {
    entry,
    statusKey,
    isLiveRow,
    isReconnectingRow,
    isSelected: selectedWorkflowId === entry.workflow_id,
    isOpening: openingId === entry.workflow_id,
    canOpen: Boolean(entry.db_path),
    rowIsRunning,
    isResumable,
    isCompletedLaneEligible,
    actionPadClass,
    isResuming: resumingId === entry.workflow_id,
    progressValue,
    papersFound: isLiveRow && liveRun ? (liveRun.papersFound ?? entry.papers_found) : entry.papers_found,
    papersIncluded:
      isLiveRow && liveRun ? (liveRun.papersIncluded ?? entry.papers_included) : entry.papers_included,
    funnelStages: isLiveRow && liveRun ? liveRun.funnelStages : undefined,
    cost: isLiveRow && liveRun ? liveRun.cost : entry.total_cost,
  }
}
