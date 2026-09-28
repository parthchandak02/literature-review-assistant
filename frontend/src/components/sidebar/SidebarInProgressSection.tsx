import { Clock, FileText, RefreshCw } from "lucide-react"
import type { HistoryEntry } from "@/lib/api"
import { Spinner } from "@/components/ui/feedback"
import { RunNavCard } from "@/components/sidebar/RunNavCard"
import { buildRunCardModel } from "@/components/sidebar/historyRowModel"
import type { LiveRun } from "@/components/sidebar/types"

export interface SidebarInProgressSectionProps {
  collapsed: boolean
  loadingHistory: boolean
  historyError: string | null
  prosperoPendingHistory: HistoryEntry[]
  inProgressHistory: HistoryEntry[]
  shouldShowStandaloneLiveCard: boolean
  liveRun: LiveRun | null
  isLiveRunSelected: boolean
  isRunning: boolean
  isMobile: boolean
  selectedWorkflowId: string | null
  openingId: string | null
  resumingId: string | null
  busyId: string | null
  wfIdCopied: string | null
  notes: Record<string, string>
  noteFlashCounters: Record<string, number>
  onRefresh: () => void
  onToggle: () => void
  onSelectLiveRun: () => void
  onCancel: () => void | Promise<void>
  onSelect: (entry: HistoryEntry) => void
  onResume: (entry: HistoryEntry) => void
  onArchive: (workflowId: string, topic?: string) => void
  onMoveToCompleted: (workflowId: string) => void
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
  prosperoPendingHistory,
  inProgressHistory,
  shouldShowStandaloneLiveCard,
  liveRun,
  isLiveRunSelected,
  isRunning,
  isMobile,
  selectedWorkflowId,
  openingId,
  resumingId,
  busyId,
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
  onMoveToCompleted,
  onCopyWorkflowId,
  onNoteChange,
  sessionResume,
  sessionArchive,
  sessionHideCompleted,
}: SidebarInProgressSectionProps) {
  const renderHistoryRow = (entry: HistoryEntry) => (
    <RunNavCard
      key={entry.workflow_id}
      model={buildRunCardModel({
        source: "in-progress",
        entry,
        liveRun,
        selectedWorkflowId,
        openingId,
        resumingId,
        options: {
          onResume: sessionResume,
          onArchive: sessionArchive,
          onHideCompleted: sessionHideCompleted,
        },
      })}
      collapsed={collapsed}
      wfIdCopied={wfIdCopied}
      noteValue={notes[entry.workflow_id] ?? ""}
      noteFlashKey={noteFlashCounters[entry.workflow_id] ?? 0}
      busy={busyId === entry.workflow_id}
      onSelectEntry={onSelect}
      onCopyWorkflowId={onCopyWorkflowId}
      onNoteChange={(val) => onNoteChange(entry.workflow_id, val)}
      onArchive={onArchive}
      onMoveToCompleted={onMoveToCompleted}
      onResume={onResume}
      onCancel={onCancel}
    />
  )

  return (
    <>
      {prosperoPendingHistory.length > 0 && (
        <section className="mb-4" aria-label="Needs your input">
          {!collapsed && (
            <div className="flex items-center justify-between px-1 mb-1.5">
              <span className="label-caps font-semibold text-muted flex items-center gap-1.5">
                <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-warning-border bg-intent-warning-subtle text-intent-warning">
                  <FileText className="h-2.5 w-2.5" />
                </span>
                Needs your input
              </span>
            </div>
          )}
          <div className="space-y-2">{prosperoPendingHistory.map(renderHistoryRow)}</div>
        </section>
      )}

    <section aria-label="In progress">
      {!collapsed && (
        <div className="flex items-center justify-between px-1 mb-1.5">
          <span className="label-caps font-semibold text-muted flex items-center gap-1.5">
            <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-primary-border bg-intent-primary-subtle text-intent-primary">
              <Clock className="h-2.5 w-2.5" />
            </span>
            In progress
          </span>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loadingHistory}
            aria-label="Refresh reviews"
            title="Refresh reviews"
            className="flex h-6 w-6 items-center justify-center rounded-control text-muted hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
        <div className="px-2 py-1.5 mb-2 rounded-md bg-intent-danger-subtle border border-intent-danger-border text-2xs text-intent-danger">
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
          <RunNavCard
            key={`live-${liveRun.runId}`}
            model={buildRunCardModel({
              source: "live",
              liveRun,
              isSelected: isLiveRunSelected,
              isRunning,
            })}
            collapsed={collapsed}
            wfIdCopied={wfIdCopied}
            isMobile={isMobile}
            onToggle={onToggle}
            onSelect={onSelectLiveRun}
            onCancel={onCancel}
            onArchive={onArchive}
            busy={busyId != null && busyId === liveRun.workflowId}
            onCopyWorkflowId={onCopyWorkflowId}
          />
        )}
        {inProgressHistory.map(renderHistoryRow)}
      </div>

      {!collapsed && !loadingHistory && inProgressHistory.length === 0 && !shouldShowStandaloneLiveCard && prosperoPendingHistory.length > 0 && (
        <p className="px-2 py-1.5 text-2xs text-muted">No reviews in progress</p>
      )}

      {!collapsed && !loadingHistory && inProgressHistory.length === 0 && !shouldShowStandaloneLiveCard && prosperoPendingHistory.length === 0 && (
        <div className="flex flex-col items-center py-6 gap-2">
          <Clock className="h-6 w-6 text-border" />
          <p className="label-muted text-center">
            Reviews you start will appear here.
          </p>
        </div>
      )}
    </section>
    </>
  )
}
