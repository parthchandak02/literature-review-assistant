import { useState, type ReactNode } from "react"
import {
  Archive,
  Check,
  MoreHorizontal,
  Play,
  RotateCcw,
  Square,
  Trash2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate } from "@/lib/format"
import type { HistoryEntry } from "@/lib/api"
import { RunStatusIndicator } from "@/components/run-status"
import { Spinner } from "@/components/ui/feedback"
import { CardProgressBar } from "@/components/sidebar/CardProgressBar"
import { NoteField } from "@/components/sidebar/NoteField"
import { RunCardMetrics } from "@/components/sidebar/RunCardMetrics"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import {
  CollapsedWorkflowBadge,
  ExpandedWorkflowBadge,
} from "@/components/sidebar/WorkflowBadges"
import type { RunCardModel } from "@/components/sidebar/historyRowModel"

export interface RunNavCardProps {
  model: RunCardModel
  collapsed: boolean
  wfIdCopied: string | null
  onCopyWorkflowId: (id: string) => Promise<void>
  onSelect?: () => void
  onSelectEntry?: (entry: HistoryEntry) => void
  isMobile?: boolean
  onToggle?: () => void
  onCancel?: () => void
  onArchive?: (workflowId: string) => void | Promise<void>
  onComplete?: (workflowId: string) => void
  onResume?: (entry: HistoryEntry) => void
  onRestoreCompleted?: (workflowId: string) => void
  onRestore?: (workflowId: string) => void
  onDelete?: (workflowId: string) => void
  archivingId?: string | null
  completingId?: string | null
  restoringCompletedId?: string | null
  restoringId?: string | null
  noteValue?: string
  noteFlashKey?: number
  onNoteChange?: (value: string) => void
  openOverflowMenuId?: string | null
  onToggleOverflowMenu?: (workflowId: string) => void
}

function ActionSpinner({ show }: { show: boolean }) {
  return show ? <Spinner size="xs" /> : null
}

export function RunNavCard({
  model,
  collapsed,
  wfIdCopied,
  onCopyWorkflowId,
  onSelect,
  onSelectEntry,
  isMobile,
  onToggle,
  onCancel,
  onArchive,
  onComplete,
  onResume,
  onRestoreCompleted,
  onRestore,
  onDelete,
  archivingId = null,
  completingId = null,
  restoringCompletedId = null,
  restoringId = null,
  noteValue = "",
  noteFlashKey = 0,
  onNoteChange,
  openOverflowMenuId = null,
  onToggleOverflowMenu,
}: RunNavCardProps) {
  const [localOverflowOpen, setLocalOverflowOpen] = useState(false)
  const workflowId = model.workflowId
  const isLane = model.variant === "completed" || model.variant === "archived"
  const showStop = !collapsed && model.rowIsRunning && onCancel && (model.variant === "live" || model.isLiveRow)
  const showArchiveInline =
    !collapsed &&
    onArchive &&
    workflowId &&
    !model.rowIsRunning &&
    model.variant === "live"
  const showResumeInline =
    !collapsed && model.isResumable && onResume && model.entry && !isLane
  const hasArchive = Boolean(onArchive && workflowId && !model.rowIsRunning)
  const hasComplete = Boolean(model.isCompletedLaneEligible && onComplete && workflowId)
  const hasResumeOverflow = Boolean(
    model.isResumable && onResume && model.entry && !showResumeInline,
  )
  const showOverflowSecondary =
    !collapsed &&
    !isLane &&
    !model.rowIsRunning &&
    [hasArchive, hasComplete, hasResumeOverflow].filter(Boolean).length >= 2

  const handleSelect = () => {
    if (model.variant === "live") {
      onSelect?.()
      if (isMobile) onToggle?.()
      return
    }
    if (model.entry && model.canOpen) {
      onSelectEntry?.(model.entry)
    }
  }

  const cardClass = cn(
    "sidebar-card",
    !isLane && "group",
    model.cardClassName,
    model.isSelected
      ? cn("sidebar-card-selected", isLane && "opacity-100")
      : model.canOpen || model.variant === "live" || isLane
        ? "sidebar-card-hover"
        : "opacity-50",
  )

  const buttonClass = cn(
    "w-full transition-colors text-left",
    collapsed
      ? "flex justify-center items-center h-9 w-9 mx-auto rounded-xl"
      : isLane
        ? "pl-2.5 pr-10 pt-3 pb-2.5"
        : "pl-2.5 pr-2 py-2.5",
    !model.canOpen && model.variant !== "live" && !isLane && "cursor-not-allowed",
  )

  const dateText =
    model.dateLabel === "Now"
      ? "Now"
      : model.dateLabel
        ? formatRunDate(model.dateLabel)
        : undefined

  const renderOverflowMenu = (menuItems: ReactNode) => {
    if (!workflowId) return null
    const isOpen = onToggleOverflowMenu
      ? openOverflowMenuId === workflowId
      : localOverflowOpen
    return (
      <div className="relative">
        <button
          onClick={(e) => {
            e.stopPropagation()
            if (onToggleOverflowMenu) {
              onToggleOverflowMenu(workflowId)
            } else {
              setLocalOverflowOpen((open) => !open)
            }
          }}
          aria-label="More actions"
          title="More actions"
          className="h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-foreground hover:bg-surface-2 transition-colors"
        >
          <MoreHorizontal className="h-3 w-3" />
        </button>
        {isOpen && (
          <div className="absolute right-9 top-0 z-40 min-w-[172px] rounded-lg border border-border/80 bg-card/95 shadow-xl backdrop-blur-sm p-1.5">
            {menuItems}
          </div>
        )}
      </div>
    )
  }

  const renderInProgressActions = () => {
    if (collapsed || isLane) return null

    if (model.variant === "live") {
      return (
        <>
          {showStop && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onCancel?.()
              }}
              aria-label="Stop run"
              title="Stop run"
              className="absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md bg-intent-danger hover:bg-intent-danger/85 text-intent-danger-fg transition-colors"
            >
              <Square className="h-2.5 w-2.5 fill-current" />
            </button>
          )}
          {showArchiveInline && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                void onArchive!(workflowId!)
              }}
              disabled={archivingId === workflowId}
              aria-label="Archive run"
              title="Archive run"
              className={cn(
                "absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md",
                "text-muted hover:text-intent-warning hover:bg-intent-warning-subtle transition-colors",
                archivingId === workflowId && "opacity-50 cursor-wait",
              )}
            >
              {archivingId === workflowId ? <Spinner size="xs" /> : <Archive className="h-3 w-3" />}
            </button>
          )}
        </>
      )
    }

    return (
      <div className="absolute top-1.5 right-1.5 flex items-center gap-0.5">
        {showStop && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onCancel?.()
            }}
            aria-label="Stop run"
            title="Stop run"
            className="flex items-center justify-center h-7 w-7 rounded-md bg-intent-danger hover:bg-intent-danger/85 text-intent-danger-fg transition-colors"
          >
            <Square className="h-2.5 w-2.5 fill-current" />
          </button>
        )}
        {showResumeInline && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onResume!(model.entry!)
            }}
            disabled={model.isResuming}
            aria-label="Resume from last checkpoint"
            title="Resume from last checkpoint"
            className={cn(
              "flex items-center justify-center h-7 w-7 rounded-md border border-intent-primary-border bg-intent-primary-subtle text-intent-primary",
              "hover:border-intent-primary-border hover:bg-intent-primary-subtle hover:text-intent-primary-fg transition-colors",
              model.isResuming && "opacity-80 cursor-wait",
            )}
          >
            {model.isResuming ? <Spinner size="xs" /> : <Play className="h-2.5 w-2.5 fill-current" />}
          </button>
        )}
        {showOverflowSecondary &&
          renderOverflowMenu(
            <>
              {onArchive && workflowId && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onArchive(workflowId)
                  }}
                  disabled={archivingId === workflowId}
                  className="w-full text-left px-2.5 py-2 text-xs font-medium rounded-md transition-colors text-muted hover:text-intent-warning hover:bg-intent-warning-subtle flex items-center gap-2 disabled:opacity-50"
                >
                  <Archive className="h-3.5 w-3.5 shrink-0" />
                  Archive run
                </button>
              )}
              {model.isCompletedLaneEligible && onComplete && workflowId && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onComplete(workflowId)
                  }}
                  disabled={completingId === workflowId}
                  className="w-full text-left px-2.5 py-2 text-xs font-medium rounded-md transition-colors text-intent-success hover:text-intent-success-fg hover:bg-intent-success-subtle flex items-center gap-2 disabled:opacity-50"
                >
                  <Check className="h-3.5 w-3.5 shrink-0" />
                  Move to completed
                </button>
              )}
              {model.isResumable && onResume && model.entry && !showResumeInline && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onResume(model.entry!)
                  }}
                  disabled={model.isResuming}
                  className="w-full text-left px-2.5 py-2 text-xs font-medium rounded-md transition-colors text-intent-primary hover:bg-intent-primary-subtle flex items-center gap-2 disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5 shrink-0" />
                  Resume run
                </button>
              )}
            </>,
          )}
        {!showOverflowSecondary && onArchive && workflowId && !model.rowIsRunning && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onArchive(workflowId)
            }}
            disabled={archivingId === workflowId}
            aria-label="Archive run"
            title="Archive run"
            className={cn(
              "flex items-center justify-center h-7 w-7 rounded-md",
              "text-muted hover:text-intent-warning hover:bg-intent-warning-subtle transition-colors",
              archivingId === workflowId && "opacity-50 cursor-wait",
            )}
          >
            {archivingId === workflowId ? <Spinner size="xs" /> : <Archive className="h-3 w-3" />}
          </button>
        )}
        {!showOverflowSecondary && model.isCompletedLaneEligible && onComplete && workflowId && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onComplete(workflowId)
            }}
            disabled={completingId === workflowId}
            aria-label="Move to completed"
            title="Move to completed"
            className={cn(
              "flex items-center justify-center h-7 w-7 rounded-md",
              "text-intent-success hover:text-intent-success-fg hover:bg-intent-success-subtle transition-colors",
              completingId === workflowId && "opacity-50 cursor-wait",
            )}
          >
            {completingId === workflowId ? (
              <Spinner size="xs" />
            ) : (
              <div className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-current">
                <Check className="h-2.5 w-2.5" />
              </div>
            )}
          </button>
        )}
      </div>
    )
  }

  const renderLaneActions = () => {
    if (collapsed || !isLane || !model.entry) return null
    const entry = model.entry

    return (
      <div className="absolute right-1.5 top-1.5 flex flex-col items-center gap-0.5">
        {model.variant === "completed" && onArchive && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onArchive(entry.workflow_id)
            }}
            disabled={archivingId === entry.workflow_id}
            aria-label="Move run to archived"
            title="Move run to archived"
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-intent-warning hover:bg-intent-warning-subtle transition-colors",
              archivingId === entry.workflow_id && "opacity-50 cursor-wait",
            )}
          >
            <ActionSpinner show={archivingId === entry.workflow_id} />
            {archivingId !== entry.workflow_id && <Archive className="h-3 w-3" />}
          </button>
        )}
        {model.variant === "completed" && onRestoreCompleted && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRestoreCompleted(entry.workflow_id)
            }}
            disabled={restoringCompletedId === entry.workflow_id}
            aria-label="Restore completed run"
            title="Restore completed run"
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-md text-intent-success/70 hover:text-intent-success-fg hover:bg-intent-success-subtle transition-colors",
              restoringCompletedId === entry.workflow_id && "opacity-50 cursor-wait",
            )}
          >
            <ActionSpinner show={restoringCompletedId === entry.workflow_id} />
            {restoringCompletedId !== entry.workflow_id && <RotateCcw className="h-3 w-3" />}
          </button>
        )}
        {model.variant === "archived" && onComplete && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onComplete(entry.workflow_id)
            }}
            disabled={completingId === entry.workflow_id}
            aria-label="Move run to completed"
            title="Move run to completed"
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-md text-intent-success/80 hover:text-intent-success hover:bg-intent-success-subtle transition-colors",
              completingId === entry.workflow_id && "opacity-50 cursor-wait",
            )}
          >
            <ActionSpinner show={completingId === entry.workflow_id} />
            {completingId !== entry.workflow_id && (
              <div className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-current">
                <Check className="h-2.5 w-2.5" />
              </div>
            )}
          </button>
        )}
        {model.variant === "archived" && onRestore && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onRestore(entry.workflow_id)
            }}
            disabled={restoringId === entry.workflow_id}
            aria-label="Restore run"
            title="Restore run"
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-intent-success hover:bg-intent-success-subtle transition-colors",
              restoringId === entry.workflow_id && "opacity-50 cursor-wait",
            )}
          >
            <ActionSpinner show={restoringId === entry.workflow_id} />
            {restoringId !== entry.workflow_id && <RotateCcw className="h-3 w-3" />}
          </button>
        )}
        {model.variant === "archived" &&
          onDelete &&
          renderOverflowMenu(
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(entry.workflow_id)
              }}
              className="w-full text-left px-2.5 py-2 text-xs font-medium rounded-md transition-colors text-intent-danger hover:text-intent-danger-fg hover:bg-intent-danger-subtle flex items-center gap-2"
            >
              <Trash2 className="h-3.5 w-3.5 shrink-0" />
              Delete permanently
            </button>,
          )}
      </div>
    )
  }

  return (
    <SidebarTooltip label={model.topic} collapsed={collapsed} side="right">
      <div className={cardClass}>
        <div className="relative">
          <button
            onClick={handleSelect}
            disabled={!model.canOpen && model.variant !== "live" && !isLane}
            className={buttonClass}
          >
            {collapsed ? (
              <CollapsedWorkflowBadge workflowId={workflowId} />
            ) : (
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-start gap-2 min-w-0">
                  {model.showWorkflowBadge && (
                    <ExpandedWorkflowBadge workflowId={workflowId} />
                  )}
                  <span
                    className={cn(
                      "text-xs text-foreground line-clamp-2 leading-snug min-w-0",
                      model.showWorkflowBadge && model.actionPadClass,
                      !model.showWorkflowBadge && isLane && "pr-0",
                    )}
                  >
                    {model.topic}
                  </span>
                </div>
                <RunCardMetrics
                  papersFound={model.papersFound}
                  papersIncluded={model.papersIncluded}
                  funnelStages={model.funnelStages}
                  cost={model.cost}
                  workflowId={workflowId}
                  copiedWorkflowId={wfIdCopied}
                  onCopyWorkflowId={onCopyWorkflowId}
                />
                <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
                  <RunStatusIndicator
                    status={model.statusKey}
                    animate={model.animateStatus}
                    loading={model.isOpening}
                    label={
                      model.isReconnectingRow
                        ? "RECONNECTING"
                        : model.statusLabel
                    }
                  />
                  {dateText && (
                    <span
                      className={cn(
                        "font-medium tabular-nums shrink-0",
                        model.dateClassName,
                      )}
                    >
                      {dateText}
                    </span>
                  )}
                </div>
              </div>
            )}
          </button>
          {renderInProgressActions()}
          {renderLaneActions()}
        </div>
        {!collapsed && model.showProgressBar && (
          <CardProgressBar status={model.statusKey} progress={model.progressValue} />
        )}
        {!collapsed && model.showNoteField && model.entry && onNoteChange && (
          <div
            className={cn(
              noteValue.trim() === "" && "hidden group-hover:block group-focus-within:block",
            )}
          >
            <NoteField
              key={`note-${model.entry.workflow_id}`}
              workflowId={model.entry.workflow_id}
              value={noteValue}
              flashKey={noteFlashKey}
              onChange={onNoteChange}
            />
          </div>
        )}
      </div>
    </SidebarTooltip>
  )
}
