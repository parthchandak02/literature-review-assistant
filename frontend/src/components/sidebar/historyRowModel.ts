import type { HistoryEntry } from "@/lib/api"
import type { RunStatus } from "@/lib/constants"
import { isProsperoPendingStatus, isReviewPendingStatus, resolveRunStatus } from "@/lib/constants"
import type { LiveRun } from "@/components/sidebar/types"

export type RunNavCardVariant = "live" | "in-progress" | "completed" | "archived"

export interface RunCardModel {
  variant: RunNavCardVariant
  entry?: HistoryEntry
  topic: string
  workflowId: string | null
  statusKey: RunStatus
  isSelected: boolean
  canOpen: boolean
  isOpening: boolean
  rowIsRunning: boolean
  isLiveRow: boolean
  isReconnectingRow: boolean
  isResumable: boolean
  isCompletedLaneEligible: boolean
  isResuming: boolean
  actionPadClass: string
  progressValue: number | undefined
  showProgressBar: boolean
  showWorkflowBadge: boolean
  showNoteField: boolean
  papersFound: number | null | undefined
  papersIncluded: number | null | undefined
  funnelStages: LiveRun["funnelStages"]
  cost: number | null | undefined
  dateLabel: string | undefined
  dateClassName: string
  cardClassName: string
  statusLabel?: string
  animateStatus: boolean
}

/** @deprecated Use RunCardModel */
export type InProgressRowModel = RunCardModel

export type BuildRunCardModelInput =
  | {
      source: "live"
      liveRun: LiveRun
      isSelected: boolean
      isRunning: boolean
    }
  | {
      source: "in-progress"
      entry: HistoryEntry
      liveRun: LiveRun | null
      selectedWorkflowId: string | null
      openingId: string | null
      resumingId: string | null
      options: {
        onResume?: (entry: HistoryEntry) => Promise<void>
        onArchive?: (workflowId: string) => Promise<void>
        onHideCompleted?: (workflowId: string) => Promise<void>
      }
    }
  | {
      source: "lane"
      entry: HistoryEntry
      variant: "completed" | "archived"
      isSelected: boolean
    }

function buildInProgressCardModel(
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
): RunCardModel {
  const isLiveRow = Boolean(
    liveRun &&
      ((entry.live_run_id && entry.live_run_id === liveRun.runId) ||
        (liveRun.workflowId && entry.workflow_id === liveRun.workflowId)),
  )
  const isProsperoPending = isProsperoPendingStatus(entry.status)
  const isReviewPending = isReviewPendingStatus(entry.status)
  const isParkedPending = isProsperoPending || isReviewPending
  const statusKey = isLiveRow && liveRun ? liveRun.status : resolveRunStatus(entry.status)
  const isReconnectingRow =
    !isLiveRow &&
    !isParkedPending &&
    !entry.live_run_id &&
    (statusKey === "streaming" || statusKey === "connecting")
  const rowIsRunning = isParkedPending
    ? false
    : isLiveRow
      ? statusKey === "streaming" || statusKey === "connecting"
      : Boolean(entry.live_run_id) || isReconnectingRow
  const isCompletedLaneEligible =
    !isParkedPending &&
    !rowIsRunning &&
    !entry.is_completed_hidden &&
    options.onHideCompleted !== undefined
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
    isParkedPending
      ? undefined
      : isLiveRow && liveRun
        ? (liveRun.phaseProgress?.value ?? (rowIsRunning ? -1 : undefined))
        : statusKey === "done"
          ? 1
          : entry.live_run_id || isReconnectingRow
            ? -1
            : undefined

  return {
    variant: "in-progress",
    entry,
    topic: entry.topic,
    workflowId: entry.workflow_id,
    statusKey,
    isSelected: selectedWorkflowId === entry.workflow_id,
    isOpening: openingId === entry.workflow_id,
    canOpen: Boolean(entry.db_path),
    rowIsRunning,
    isLiveRow,
    isReconnectingRow,
    isResumable,
    isCompletedLaneEligible,
    isResuming: resumingId === entry.workflow_id,
    actionPadClass,
    progressValue,
    showProgressBar: true,
    showWorkflowBadge: true,
    showNoteField: true,
    papersFound: isLiveRow && liveRun ? (liveRun.papersFound ?? entry.papers_found) : entry.papers_found,
    papersIncluded:
      isLiveRow && liveRun ? (liveRun.papersIncluded ?? entry.papers_included) : entry.papers_included,
    funnelStages: isLiveRow && liveRun ? liveRun.funnelStages : undefined,
    cost: isLiveRow && liveRun ? liveRun.cost : entry.total_cost,
    dateLabel: entry.created_at ?? undefined,
    dateClassName: "text-muted",
    cardClassName: "",
    statusLabel: undefined,
    animateStatus: rowIsRunning,
  }
}

function buildLiveCardModel(
  liveRun: LiveRun,
  isSelected: boolean,
  isRunning: boolean,
): RunCardModel {
  const actionPadClass =
    (liveRun.workflowId && !isRunning) || (isRunning) ? "pr-12" : ""

  return {
    variant: "live",
    topic: liveRun.topic,
    workflowId: liveRun.workflowId ?? null,
    statusKey: liveRun.status,
    isSelected,
    isOpening: false,
    canOpen: true,
    rowIsRunning: isRunning,
    isLiveRow: true,
    isReconnectingRow: false,
    isResumable: false,
    isCompletedLaneEligible: false,
    isResuming: false,
    actionPadClass,
    progressValue: liveRun.phaseProgress?.value,
    showProgressBar: true,
    showWorkflowBadge: true,
    showNoteField: false,
    papersFound: liveRun.papersFound,
    papersIncluded: liveRun.papersIncluded,
    funnelStages: liveRun.funnelStages,
    cost: liveRun.cost,
    dateLabel: liveRun.startedAt ?? "Now",
    dateClassName: "text-muted",
    cardClassName: "",
    animateStatus: isRunning,
  }
}

function buildLaneCardModel(
  entry: HistoryEntry,
  variant: "completed" | "archived",
  isSelected: boolean,
): RunCardModel {
  const statusKey = resolveRunStatus(entry.status)
  const cardClassName =
    variant === "completed"
      ? "sidebar-card-hover relative min-h-[120px] opacity-90 bg-intent-success-subtle border-intent-success-border"
      : "sidebar-card-hover relative min-h-[120px] sidebar-card-archived opacity-85"

  return {
    variant,
    entry,
    topic: entry.topic,
    workflowId: entry.workflow_id,
    statusKey,
    isSelected,
    isOpening: false,
    canOpen: true,
    rowIsRunning: false,
    isLiveRow: false,
    isReconnectingRow: false,
    isResumable: false,
    isCompletedLaneEligible: false,
    isResuming: false,
    actionPadClass: "",
    progressValue: undefined,
    showProgressBar: false,
    showWorkflowBadge: false,
    showNoteField: false,
    papersFound: entry.papers_found,
    papersIncluded: entry.papers_included,
    funnelStages: undefined,
    cost: entry.total_cost,
    dateLabel: entry.created_at ?? undefined,
    dateClassName:
      variant === "completed" ? "text-intent-success-fg/60" : "text-muted",
    cardClassName,
    animateStatus: false,
  }
}

export function buildRunCardModel(input: BuildRunCardModelInput): RunCardModel {
  switch (input.source) {
    case "live":
      return buildLiveCardModel(input.liveRun, input.isSelected, input.isRunning)
    case "in-progress":
      return buildInProgressCardModel(
        input.entry,
        input.liveRun,
        input.selectedWorkflowId,
        input.openingId,
        input.resumingId,
        input.options,
      )
    case "lane":
      return buildLaneCardModel(input.entry, input.variant, input.isSelected)
  }
}

/** @deprecated Use buildRunCardModel with source: "in-progress" */
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
): RunCardModel {
  return buildRunCardModel({
    source: "in-progress",
    entry,
    liveRun,
    selectedWorkflowId,
    openingId,
    resumingId,
    options,
  })
}
