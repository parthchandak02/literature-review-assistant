import { useId, type ReactNode } from "react"
import { Archive, Check, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import type { HistoryEntry } from "@/lib/api"
import { RunNavCard } from "@/components/sidebar/RunNavCard"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import { buildRunCardModel } from "@/components/sidebar/historyRowModel"

export interface SidebarCompletedArchivedSectionProps {
  completedHistory: HistoryEntry[]
  archivedHistory: HistoryEntry[]
  completedExpanded: boolean
  archivedExpanded: boolean
  collapsed: boolean
  selectedWorkflowId: string | null
  wfIdCopied: string | null
  busyId: string | null
  onToggleCompleted: () => void
  onToggleArchived: () => void
  /** Collapsed rail: expand the sidebar and open the given lane. */
  onOpenLane: (lane: "completed" | "archived") => void
  onSelect: (entry: HistoryEntry) => void
  onCopyWorkflowId: (id: string) => Promise<void>
  onArchive: (id: string, topic?: string) => void
  onMoveToCompleted: (id: string) => void
  onMoveToInProgress: (id: string) => void
  onDelete: (id: string) => void
}

function LaneIcon({ lane }: { lane: "completed" | "archived" }) {
  return lane === "completed" ? (
    <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-intent-success-border bg-intent-success-subtle text-intent-success">
      <Check className="h-2.5 w-2.5" aria-hidden />
    </span>
  ) : (
    <span className="flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border border-border bg-surface-2 text-muted">
      <Archive className="h-2.5 w-2.5" aria-hidden />
    </span>
  )
}

function CollapsedLaneButton({
  lane,
  label,
  count,
  onClick,
}: {
  lane: "completed" | "archived"
  label: string
  count: number
  onClick: () => void
}) {
  const Icon = lane === "completed" ? Check : Archive
  return (
    <SidebarTooltip label={`${label} (${count})`} collapsed side="right">
      <button
        type="button"
        onClick={onClick}
        aria-label={`${label}, ${count} ${count === 1 ? "review" : "reviews"}`}
        className={cn(
          "relative flex h-9 w-9 mx-auto items-center justify-center rounded-xl transition-colors hover:bg-surface-2/60",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          lane === "completed" ? "text-intent-success" : "text-muted hover:text-foreground",
        )}
      >
        <Icon className="h-4 w-4" aria-hidden />
        {count > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-pill border border-border bg-surface-2 px-1 text-2xs font-semibold tabular-nums text-foreground"
            aria-hidden
          >
            {count}
          </span>
        )}
      </button>
    </SidebarTooltip>
  )
}

function Lane({
  label,
  lane,
  count,
  expanded,
  onToggle,
  emptyText,
  children,
}: {
  label: string
  lane: "completed" | "archived"
  count: number
  expanded: boolean
  onToggle: () => void
  emptyText: string
  children: ReactNode
}) {
  const listId = useId()
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={listId}
        className={cn(
          "w-full flex items-center justify-between px-1.5 py-1 rounded-control transition-colors",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          lane === "completed"
            ? "text-intent-success-text hover:bg-intent-success-subtle"
            : "text-muted hover:text-foreground hover:bg-surface-2/60",
        )}
      >
        <span className="label-caps font-semibold flex items-center gap-1.5">
          <LaneIcon lane={lane} />
          {label} ({count})
        </span>
        <ChevronRight
          className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-90")}
          aria-hidden
        />
      </button>
      {expanded && (
        <div id={listId} className="mb-2 mt-1 max-h-64 overflow-y-auto space-y-1.5 pr-0.5">
          {count === 0 ? <p className="px-2 py-1.5 text-2xs text-muted">{emptyText}</p> : children}
        </div>
      )}
    </div>
  )
}

export function SidebarCompletedArchivedSection({
  completedHistory,
  archivedHistory,
  completedExpanded,
  archivedExpanded,
  collapsed,
  selectedWorkflowId,
  wfIdCopied,
  busyId,
  onToggleCompleted,
  onToggleArchived,
  onOpenLane,
  onSelect,
  onCopyWorkflowId,
  onArchive,
  onMoveToCompleted,
  onMoveToInProgress,
  onDelete,
}: SidebarCompletedArchivedSectionProps) {
  if (collapsed) {
    return (
      <section
        aria-label="Completed and archived reviews"
        className="relative z-10 border-t border-border/80 py-2 shrink-0 flex flex-col gap-1"
      >
        <CollapsedLaneButton
          lane="completed"
          label="Completed"
          count={completedHistory.length}
          onClick={() => onOpenLane("completed")}
        />
        <CollapsedLaneButton
          lane="archived"
          label="Archived"
          count={archivedHistory.length}
          onClick={() => onOpenLane("archived")}
        />
      </section>
    )
  }

  const renderLaneCard = (entry: HistoryEntry, variant: "completed" | "archived") => (
    <RunNavCard
      key={`${variant}-${entry.workflow_id}`}
      model={buildRunCardModel({
        source: "lane",
        entry,
        variant,
        isSelected: selectedWorkflowId === entry.workflow_id,
      })}
      collapsed={false}
      wfIdCopied={wfIdCopied}
      busy={busyId === entry.workflow_id}
      onSelectEntry={onSelect}
      onCopyWorkflowId={onCopyWorkflowId}
      onArchive={onArchive}
      onMoveToCompleted={onMoveToCompleted}
      onMoveToInProgress={onMoveToInProgress}
      onDelete={onDelete}
    />
  )

  return (
    <section
      aria-label="Completed and archived reviews"
      className="relative z-10 border-t border-border/80 px-2 py-2 shrink-0 space-y-1"
    >
      <Lane
        label="Completed"
        lane="completed"
        count={completedHistory.length}
        expanded={completedExpanded}
        onToggle={onToggleCompleted}
        emptyText="No completed reviews"
      >
        {completedHistory.map((entry) => renderLaneCard(entry, "completed"))}
      </Lane>
      <Lane
        label="Archived"
        lane="archived"
        count={archivedHistory.length}
        expanded={archivedExpanded}
        onToggle={onToggleArchived}
        emptyText="No archived reviews"
      >
        {archivedHistory.map((entry) => renderLaneCard(entry, "archived"))}
      </Lane>
    </section>
  )
}
