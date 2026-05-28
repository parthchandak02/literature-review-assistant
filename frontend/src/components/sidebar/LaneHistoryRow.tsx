import { Archive, Check, MoreHorizontal, RotateCcw, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate } from "@/lib/format"
import { STATUS_LABEL, STATUS_TEXT, resolveRunStatus } from "@/lib/constants"
import type { HistoryEntry } from "@/lib/api"
import { StatusPulse } from "@/components/run-status"
import { Spinner } from "@/components/ui/feedback"
import { RunCardMetrics } from "@/components/sidebar/RunCardMetrics"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"

export type HistoryLaneVariant = "completed" | "archived"

export interface LaneHistoryRowProps {
  entry: HistoryEntry
  variant: HistoryLaneVariant
  collapsed: boolean
  isSelected: boolean
  wfIdCopied: string | null
  archivingId?: string | null
  restoringCompletedId?: string | null
  completingId?: string | null
  restoringId?: string | null
  openArchivedMenuId?: string | null
  onSelect: (entry: HistoryEntry) => void
  onCopyWorkflowId: (id: string) => Promise<void>
  onArchive?: (workflowId: string) => void
  onRestoreCompleted?: (workflowId: string) => void
  onComplete?: (workflowId: string) => void
  onRestore?: (workflowId: string) => void
  onToggleArchivedMenu?: (workflowId: string) => void
  onDelete?: (workflowId: string) => void
}

export function LaneHistoryRow({
  entry,
  variant,
  collapsed,
  isSelected,
  wfIdCopied,
  archivingId = null,
  restoringCompletedId = null,
  completingId = null,
  restoringId = null,
  openArchivedMenuId = null,
  onSelect,
  onCopyWorkflowId,
  onArchive,
  onRestoreCompleted,
  onComplete,
  onRestore,
  onToggleArchivedMenu,
  onDelete,
}: LaneHistoryRowProps) {
  const statusKey = resolveRunStatus(entry.status)
  const cardClass =
    variant === "completed"
      ? cn(
          "sidebar-card sidebar-card-hover relative min-h-[120px]",
          "opacity-90 bg-intent-success-subtle border-intent-success-border",
          isSelected && "sidebar-card-selected opacity-100",
        )
      : cn(
          "sidebar-card sidebar-card-hover relative min-h-[120px]",
          "sidebar-card-archived opacity-85",
          isSelected && "sidebar-card-selected opacity-100",
        )

  return (
    <SidebarTooltip
      key={`${variant}-${entry.workflow_id}`}
      label={entry.topic}
      collapsed={collapsed}
      side="right"
    >
      <div className={cardClass}>
        <button
          onClick={() => onSelect(entry)}
          className="w-full transition-colors text-left pl-2.5 pr-10 pt-3 pb-2.5"
        >
          <div className="flex flex-col gap-1 min-w-0">
            <span className="text-xs text-foreground line-clamp-2 leading-snug">{entry.topic}</span>
            <RunCardMetrics
              papersFound={entry.papers_found}
              papersIncluded={entry.papers_included}
              cost={entry.total_cost}
              workflowId={entry.workflow_id}
              copiedWorkflowId={wfIdCopied}
              onCopyWorkflowId={onCopyWorkflowId}
            />
            <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
              <div className="flex items-center gap-1.5 shrink-0">
                <StatusPulse status={statusKey} size="xs" />
                <span className={cn("font-semibold uppercase tracking-wide", STATUS_TEXT[statusKey])}>
                  {STATUS_LABEL[statusKey]}
                </span>
              </div>
              {entry.created_at && (
                <span
                  className={cn(
                    "font-medium tabular-nums shrink-0",
                    variant === "completed" ? "text-intent-success-fg/60" : "text-muted",
                  )}
                >
                  {formatRunDate(entry.created_at)}
                </span>
              )}
            </div>
          </div>
        </button>

        <div className="absolute right-1.5 top-1.5 flex flex-col items-center gap-0.5">
          {variant === "completed" && onArchive && (
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
              {archivingId === entry.workflow_id ? <Spinner size="xs" /> : <Archive className="h-3 w-3" />}
            </button>
          )}
          {variant === "completed" && onRestoreCompleted && (
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
              {restoringCompletedId === entry.workflow_id ? (
                <Spinner size="xs" />
              ) : (
                <RotateCcw className="h-3 w-3" />
              )}
            </button>
          )}
          {variant === "archived" && onComplete && (
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
              {completingId === entry.workflow_id ? (
                <Spinner size="xs" />
              ) : (
                <div className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-current">
                  <Check className="h-2.5 w-2.5" />
                </div>
              )}
            </button>
          )}
          {variant === "archived" && onRestore && (
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
              {restoringId === entry.workflow_id ? <Spinner size="xs" /> : <RotateCcw className="h-3 w-3" />}
            </button>
          )}
          {variant === "archived" && onDelete && onToggleArchivedMenu && (
            <div className="relative">
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleArchivedMenu(entry.workflow_id)
                }}
                aria-label="More actions"
                title="More actions"
                className="h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-foreground hover:bg-surface-2 transition-colors"
              >
                <MoreHorizontal className="h-3 w-3" />
              </button>
              {openArchivedMenuId === entry.workflow_id && (
                <div className="absolute right-9 top-0 z-40 min-w-[172px] rounded-lg border border-border/80 bg-card/95 shadow-xl backdrop-blur-sm p-1.5">
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
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </SidebarTooltip>
  )
}
