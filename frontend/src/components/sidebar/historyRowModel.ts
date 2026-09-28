import type { HistoryEntry } from "@/lib/api"
import type { RunStatus } from "@/lib/constants"
import {
  isProsperoPendingStatus,
  isReviewPendingStatus,
  resolveRunStatus,
  runStatusLabel,
} from "@/lib/constants"
import type { LiveRun } from "@/components/sidebar/types"

/** Shorten a topic on a word boundary for dialogs and toasts. */
export function truncateTopic(topic: string, max = 60): string {
  const clean = topic.trim().replace(/\s+/g, " ")
  if (clean.length <= max) return clean
  const cut = clean.slice(0, max - 1)
  const lastSpace = cut.lastIndexOf(" ")
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).replace(/[\s,;:.-]+$/, "")}…`
}

function fmtNum(n: number): string {
  return n.toLocaleString()
}

export function resolveSummaryCounts(
  papersFound: number | null | undefined,
  papersIncluded: number | null | undefined,
  funnelStages: LiveRun["funnelStages"],
): { found: number | null; included: number | null } {
  let found = papersFound ?? null
  let included = papersIncluded ?? null

  if (funnelStages != null && funnelStages.length > 0) {
    if (found == null) found = funnelStages[0]?.count ?? null
    const includedStage = funnelStages.find((s) => s.key === "included")
    if (included == null && includedStage != null) included = includedStage.count
  }

  return { found, included }
}

export interface RunCardMetricsInput {
  papersFound?: number | null
  papersIncluded?: number | null
  funnelStages?: LiveRun["funnelStages"]
  cost?: number | null
}

/** The one number a collapsed card shows: included count once search has run, else found. */
export function keyMetricText({ papersFound, papersIncluded, funnelStages }: RunCardMetricsInput): string | null {
  const { found, included } = resolveSummaryCounts(papersFound, papersIncluded, funnelStages)
  if (found == null || found <= 0) return null
  if (included != null) return `${fmtNum(included)} included`
  return `${fmtNum(found)} found`
}

export function hasRunCardDetails(input: RunCardMetricsInput): boolean {
  return keyMetricText(input) != null || (input.cost != null && input.cost > 0)
}

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
  /** Why the card cannot be opened; shown as a subtitle and tooltip. */
  disabledReason?: string
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
        : statusKey === "done" || statusKey === "needs_revision"
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
    statusLabel: isReconnectingRow
      ? runStatusLabel("reconnecting")
      : runStatusLabel(isLiveRow ? statusKey : entry.status),
    disabledReason: entry.db_path ? undefined : "No database yet",
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
    statusLabel: runStatusLabel(liveRun.status),
    animateStatus: isRunning,
  }
}

function buildLaneCardModel(
  entry: HistoryEntry,
  variant: "completed" | "archived",
  isSelected: boolean,
): RunCardModel {
  const statusKey = resolveRunStatus(entry.status)
  const cardClassName = variant === "archived" ? "sidebar-card-archived" : ""

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
    showWorkflowBadge: true,
    showNoteField: false,
    papersFound: entry.papers_found,
    papersIncluded: entry.papers_included,
    funnelStages: undefined,
    cost: entry.total_cost,
    dateLabel: entry.created_at ?? undefined,
    dateClassName: "text-muted",
    cardClassName,
    statusLabel: runStatusLabel(entry.status),
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
