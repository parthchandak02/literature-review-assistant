import { Archive, Check, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import type { HistoryEntry } from "@/lib/api"
import { LaneHistoryRow } from "@/components/sidebar/LaneHistoryRow"

export interface SidebarCompletedArchivedSectionProps {
  completedHistory: HistoryEntry[]
  archivedHistory: HistoryEntry[]
  completedExpanded: boolean
  archivedExpanded: boolean
  collapsed: boolean
  selectedWorkflowId: string | null
  wfIdCopied: string | null
  archivingId: string | null
  restoringCompletedId: string | null
  completingId: string | null
  restoringId: string | null
  openArchivedMenuId: string | null
  onToggleCompleted: () => void
  onToggleArchived: () => void
  onSelect: (entry: HistoryEntry) => void
  onCopyWorkflowId: (id: string) => Promise<void>
  onArchive: (id: string) => void
  onRestoreCompleted: (id: string) => void
  onComplete: (id: string) => void
  onRestore: (id: string) => void
  onToggleArchivedMenu: (id: string) => void
  onDelete: (id: string) => void
}

export function SidebarCompletedArchivedSection({
  completedHistory,
  archivedHistory,
  completedExpanded,
  archivedExpanded,
  collapsed,
  selectedWorkflowId,
  wfIdCopied,
  archivingId,
  restoringCompletedId,
  completingId,
  restoringId,
  openArchivedMenuId,
  onToggleCompleted,
  onToggleArchived,
  onSelect,
  onCopyWorkflowId,
  onArchive,
  onRestoreCompleted,
  onComplete,
  onRestore,
  onToggleArchivedMenu,
  onDelete,
}: SidebarCompletedArchivedSectionProps) {
  if (collapsed) return null

  return (
    <section className="relative z-10 border-t border-border/80 px-2 py-2 shrink-0">
      <button
        type="button"
        onClick={onToggleCompleted}
        className="mb-1 w-full flex items-center justify-between px-1.5 py-1 rounded-md text-intent-success hover:text-intent-success-fg hover:bg-intent-success-subtle transition-colors"
      >
        <span className="label-caps font-semibold flex items-center gap-1.5">
          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-success-border bg-intent-success-subtle text-intent-success">
            <Check className="h-2.5 w-2.5" />
          </span>
          Completed ({completedHistory.length})
        </span>
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            completedExpanded && "rotate-90",
          )}
        />
      </button>
      {completedExpanded && (
        <div className="mb-2 mt-1 max-h-48 overflow-y-auto space-y-1.5 pr-0.5">
          {completedHistory.length === 0 ? (
            <p className="px-2 py-1.5 text-[11px] text-intent-success/55">
              No runs in completed.
            </p>
          ) : (
            completedHistory.map((entry) => (
              <LaneHistoryRow
                key={`completed-${entry.workflow_id}`}
                entry={entry}
                variant="completed"
                collapsed={collapsed}
                isSelected={selectedWorkflowId === entry.workflow_id}
                wfIdCopied={wfIdCopied}
                archivingId={archivingId}
                restoringCompletedId={restoringCompletedId}
                onSelect={(row) => onSelect(row)}
                onCopyWorkflowId={onCopyWorkflowId}
                onArchive={(id) => onArchive(id)}
                onRestoreCompleted={(id) => onRestoreCompleted(id)}
              />
            ))
          )}
        </div>
      )}
      <button
        type="button"
        onClick={onToggleArchived}
        className="w-full flex items-center justify-between px-1.5 py-1 rounded-md text-muted hover:text-foreground hover:bg-surface-2/60 transition-colors"
      >
        <span className="label-caps font-semibold flex items-center gap-1.5">
          <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-warning-border bg-intent-warning-subtle text-intent-warning">
            <Archive className="h-2.5 w-2.5" />
          </span>
          Archived ({archivedHistory.length})
        </span>
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            archivedExpanded && "rotate-90",
          )}
        />
      </button>
      {archivedExpanded && (
        <div className="mt-1 max-h-48 overflow-y-auto space-y-1.5 pr-0.5">
          {archivedHistory.length === 0 ? (
            <p className="px-2 py-1.5 text-[11px] text-muted">
              No archived chats.
            </p>
          ) : (
            archivedHistory.map((entry) => (
              <LaneHistoryRow
                key={`archived-${entry.workflow_id}`}
                entry={entry}
                variant="archived"
                collapsed={collapsed}
                isSelected={selectedWorkflowId === entry.workflow_id}
                wfIdCopied={wfIdCopied}
                completingId={completingId}
                restoringId={restoringId}
                openArchivedMenuId={openArchivedMenuId}
                onSelect={(row) => onSelect(row)}
                onCopyWorkflowId={onCopyWorkflowId}
                onComplete={(id) => onComplete(id)}
                onRestore={(id) => onRestore(id)}
                onToggleArchivedMenu={onToggleArchivedMenu}
                onDelete={onDelete}
              />
            ))
          )}
        </div>
      )}
    </section>
  )
}
