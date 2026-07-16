import { Clock, RefreshCw } from "lucide-react"
import type { HistoryEntry } from "@/lib/api"
import { Spinner } from "@/components/ui/feedback"
import { LiveRunCard } from "@/components/sidebar/LiveRunCard"
import { InProgressHistoryRow } from "@/components/sidebar/InProgressHistoryRow"
import { buildInProgressRowModel } from "@/components/sidebar/historyRowModel"
import type { LiveRun } from "@/components/sidebar/types"

export interface SidebarInProgressSectionProps {
  collapsed: boolean
  loadingHistory: boolean
  historyError: string | null
  inProgressHistory: HistoryEntry[]
  shouldShowStandaloneLiveCard: boolean
  liveRun: LiveRun | null
  isLiveRunSelected: boolean
  isRunning: boolean
  isMobile: boolean
  selectedWorkflowId: string | null
  openingId: string | null
  resumingId: string | null
  archivingId: string | null
  completingId: string | null
  wfIdCopied: string | null
  notes: Record<string, string>
  noteFlashCounters: Record<string, number>
  onRefresh: () => void
  onToggle: () => void
  onSelectLiveRun: () => void
  onCancel: () => void
  onSelect: (entry: HistoryEntry) => void
  onResume: (entry: HistoryEntry) => void
  onArchive: (workflowId: string) => Promise<void>
  onComplete: (workflowId: string) => void
  onCopyWorkflowId: (id: string) => Promise<void>
  onNoteChange: (workflowId: string, value: string) => void
  /** Session handlers passed through to row model builder. */
  sessionResume: (entry: HistoryEntry) => Promise<void>
  sessionArchive: (workflowId: string) => Promise<void>
  sessionHideCompleted: (workflowId: string) => Promise<void>
}

export function SidebarInProgressSection({
  collapsed,
  loadingHistory,
  historyError,
  inProgressHistory,
  shouldShowStandaloneLiveCard,
  liveRun,
  isLiveRunSelected,
  isRunning,
  isMobile,
  selectedWorkflowId,
  openingId,
  resumingId,
  archivingId,
  completingId,
  wfIdCopied,
  notes,
  noteFlashCounters,
  onRefresh,
  onToggle,
  onSelectLiveRun,
  onCancel,
  onSelect,
  onResume,
  onArchive,
  onComplete,
  onCopyWorkflowId,
  onNoteChange,
  sessionResume,
  sessionArchive,
  sessionHideCompleted,
}: SidebarInProgressSectionProps) {
  return (
    <section>
      {!collapsed && (
        <div className="flex items-center justify-between px-1 mb-1.5">
          <span className="label-caps font-semibold text-muted flex items-center gap-1.5">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-primary-border bg-intent-primary-subtle text-intent-primary">
              <Clock className="h-2.5 w-2.5" />
            </span>
            In Progress
          </span>
          <button
            onClick={onRefresh}
            disabled={loadingHistory}
            aria-label="Refresh history"
            className="text-muted hover:text-foreground transition-colors"
          >
            {loadingHistory ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
          </button>
        </div>
      )}

      {historyError && !collapsed && (
        <div className="px-2 py-1.5 mb-2 rounded-md bg-intent-danger-subtle border border-intent-danger-border text-[11px] text-intent-danger">
          {historyError}
        </div>
      )}

      {loadingHistory && inProgressHistory.length === 0 && !liveRun && !collapsed && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="sidebar-card px-3 py-3">
              <div className="h-2.5 bg-surface-3/50 rounded animate-pulse w-3/4 mb-2" />
              <div className="h-2 bg-surface-3/50 rounded animate-pulse w-1/2" />
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {shouldShowStandaloneLiveCard && liveRun && (
          <LiveRunCard
            liveRun={liveRun}
            collapsed={collapsed}
            isLiveRunSelected={isLiveRunSelected}
            isRunning={isRunning}
            isMobile={isMobile}
            onToggle={onToggle}
            onSelectLiveRun={onSelectLiveRun}
            onCancel={onCancel}
            onArchive={async (workflowId) => { await onArchive(workflowId) }}
            archivingId={archivingId}
            wfIdCopied={wfIdCopied}
            onCopyWorkflowId={onCopyWorkflowId}
          />
        )}
        {inProgressHistory.map((entry) => (
          <InProgressHistoryRow
            key={entry.workflow_id}
            model={buildInProgressRowModel(
              entry,
              liveRun,
              selectedWorkflowId,
              openingId,
              resumingId,
              {
                onResume: sessionResume,
                onArchive: sessionArchive,
                onHideCompleted: sessionHideCompleted,
              },
            )}
            collapsed={collapsed}
            wfIdCopied={wfIdCopied}
            noteValue={notes[entry.workflow_id] ?? ""}
            noteFlashKey={noteFlashCounters[entry.workflow_id] ?? 0}
            archivingId={archivingId}
            completingId={completingId}
            onSelect={onSelect}
            onCopyWorkflowId={onCopyWorkflowId}
            onNoteChange={(val) => onNoteChange(entry.workflow_id, val)}
            onArchive={onArchive}
            onComplete={onComplete}
            onResume={onResume}
            onCancel={onCancel}
          />
        ))}
      </div>

      {!collapsed && !loadingHistory && inProgressHistory.length === 0 && !shouldShowStandaloneLiveCard && (
        <div className="flex flex-col items-center py-6 gap-2">
          <Clock className="h-6 w-6 text-border" />
          <p className="label-muted text-center">
            Past reviews will appear here automatically.
          </p>
        </div>
      )}
    </section>
  )
}
