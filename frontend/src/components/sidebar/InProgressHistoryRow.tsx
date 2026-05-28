import { Archive, Check, Play, Square } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate } from "@/lib/format"
import { STATUS_LABEL, STATUS_TEXT } from "@/lib/constants"
import type { HistoryEntry } from "@/lib/api"
import { StatusPulse } from "@/components/run-status"
import { Spinner } from "@/components/ui/feedback"
import { CardProgressBar } from "@/components/sidebar/CardProgressBar"
import { NoteField } from "@/components/sidebar/NoteField"
import { RunCardMetrics } from "@/components/sidebar/RunCardMetrics"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import {
  CollapsedWorkflowBadge,
  ExpandedWorkflowBadge,
} from "@/components/sidebar/WorkflowBadges"
import type { InProgressRowModel } from "@/components/sidebar/historyRowModel"

export interface InProgressHistoryRowProps {
  model: InProgressRowModel
  collapsed: boolean
  wfIdCopied: string | null
  noteValue: string
  noteFlashKey: number
  archivingId: string | null
  completingId: string | null
  onSelect: (entry: HistoryEntry) => void
  onCopyWorkflowId: (id: string) => Promise<void>
  onNoteChange: (value: string) => void
  onArchive?: (workflowId: string) => void
  onComplete?: (workflowId: string) => void
  onResume?: (entry: HistoryEntry) => void
  onCancel?: () => void
}

export function InProgressHistoryRow({
  model,
  collapsed,
  wfIdCopied,
  noteValue,
  noteFlashKey,
  archivingId,
  completingId,
  onSelect,
  onCopyWorkflowId,
  onNoteChange,
  onArchive,
  onComplete,
  onResume,
  onCancel,
}: InProgressHistoryRowProps) {
  const { entry } = model

  return (
    <SidebarTooltip label={entry.topic} collapsed={collapsed} side="right">
      <div
        className={cn(
          "sidebar-card",
          model.isSelected
            ? "sidebar-card-selected"
            : model.canOpen
              ? "sidebar-card-hover"
              : "opacity-50",
        )}
      >
        <div className="relative">
          <button
            onClick={() => model.canOpen && onSelect(entry)}
            disabled={!model.canOpen}
            className={cn(
              "w-full transition-colors text-left",
              collapsed
                ? "flex justify-center items-center h-9 w-9 mx-auto rounded-xl"
                : "pl-2.5 pr-2 py-2.5",
              !model.canOpen && "cursor-not-allowed",
            )}
          >
            {collapsed ? (
              <CollapsedWorkflowBadge workflowId={entry.workflow_id} />
            ) : (
              <div className="flex flex-col gap-1 min-w-0">
                <div className="flex items-start gap-2 min-w-0">
                  <ExpandedWorkflowBadge workflowId={entry.workflow_id} />
                  <span
                    className={cn(
                      "text-xs text-foreground line-clamp-2 leading-snug min-w-0",
                      model.actionPadClass,
                    )}
                  >
                    {entry.topic}
                  </span>
                </div>
                <RunCardMetrics
                  papersFound={model.papersFound}
                  papersIncluded={model.papersIncluded}
                  funnelStages={model.funnelStages}
                  cost={model.cost}
                  workflowId={entry.workflow_id}
                  copiedWorkflowId={wfIdCopied}
                  onCopyWorkflowId={onCopyWorkflowId}
                />
                <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
                  <div className="flex items-center gap-1.5 shrink-0">
                    {model.isOpening ? (
                      <Spinner size="xs" />
                    ) : (
                      <StatusPulse
                        status={model.statusKey}
                        animate={model.rowIsRunning}
                        size="xs"
                      />
                    )}
                    <span
                      className={cn(
                        "font-semibold uppercase tracking-wide",
                        STATUS_TEXT[model.statusKey],
                      )}
                    >
                      {model.isReconnectingRow ? "RECONNECTING" : STATUS_LABEL[model.statusKey]}
                    </span>
                  </div>
                  {entry.created_at && (
                    <span className="text-muted font-medium tabular-nums shrink-0">
                      {formatRunDate(entry.created_at)}
                    </span>
                  )}
                </div>
              </div>
            )}
          </button>

          {!collapsed && (
            <div className="absolute top-1.5 right-1.5 flex items-center gap-0.5">
              {model.isLiveRow && model.rowIsRunning && onCancel && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onCancel()
                  }}
                  aria-label="Stop run"
                  title="Stop run"
                  className="flex items-center justify-center h-7 w-7 rounded-md bg-intent-danger hover:bg-intent-danger/85 text-intent-danger-fg transition-colors"
                >
                  <Square className="h-2.5 w-2.5 fill-current" />
                </button>
              )}
              {onArchive && !model.rowIsRunning && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onArchive(entry.workflow_id)
                  }}
                  disabled={archivingId === entry.workflow_id}
                  aria-label="Archive run"
                  title="Archive run"
                  className={cn(
                    "flex items-center justify-center h-7 w-7 rounded-md",
                    "text-muted hover:text-intent-warning hover:bg-intent-warning-subtle transition-colors",
                    archivingId === entry.workflow_id && "opacity-50 cursor-wait",
                  )}
                >
                  {archivingId === entry.workflow_id ? (
                    <Spinner size="xs" />
                  ) : (
                    <Archive className="h-3 w-3" />
                  )}
                </button>
              )}
              {model.isCompletedLaneEligible && onComplete && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onComplete(entry.workflow_id)
                  }}
                  disabled={completingId === entry.workflow_id}
                  aria-label="Move to completed"
                  title="Move to completed"
                  className={cn(
                    "flex items-center justify-center h-7 w-7 rounded-md",
                    "text-intent-success hover:text-intent-success-fg hover:bg-intent-success-subtle transition-colors",
                    completingId === entry.workflow_id && "opacity-50 cursor-wait",
                  )}
                >
                  {completingId === entry.workflow_id ? (
                    <Spinner size="xs" />
                  ) : (
                    <div className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-current">
                      <Check className="h-2.5 w-2.5" />
                    </div>
                  )}
                </button>
              )}
              {model.isResumable && onResume && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onResume(entry)
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
                  {model.isResuming ? (
                    <Spinner size="xs" />
                  ) : (
                    <Play className="h-2.5 w-2.5 fill-current" />
                  )}
                </button>
              )}
            </div>
          )}
        </div>
        {!collapsed && (
          <CardProgressBar status={model.statusKey} progress={model.progressValue} />
        )}
        {!collapsed && (
          <NoteField
            key={`note-${entry.workflow_id}`}
            workflowId={entry.workflow_id}
            value={noteValue}
            flashKey={noteFlashKey}
            onChange={onNoteChange}
          />
        )}
      </div>
    </SidebarTooltip>
  )
}
