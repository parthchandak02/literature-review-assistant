import { useId, useRef, useState } from "react"
import {
  Archive,
  CheckSquare,
  Clock,
  MoreHorizontal,
  Play,
  Square,
  StickyNote,
  Trash2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate, formatShortDate, formatWorkflowId } from "@/lib/format"
import type { HistoryEntry } from "@/lib/api"
import { RunStatusIndicator } from "@/components/run-status"
import { Spinner } from "@/components/ui/feedback"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { CardProgressBar } from "@/components/sidebar/CardProgressBar"
import { NoteField } from "@/components/sidebar/NoteField"
import { RunCardDetails, RunCardDetailsToggle } from "@/components/sidebar/RunCardMetrics"
import { SidebarTooltip } from "@/components/sidebar/SidebarTooltip"
import {
  CollapsedWorkflowBadge,
  ExpandedWorkflowBadge,
} from "@/components/sidebar/WorkflowBadges"
import {
  hasRunCardDetails,
  keyMetricText,
  type RunCardModel,
} from "@/components/sidebar/historyRowModel"

export interface RunNavCardProps {
  model: RunCardModel
  collapsed: boolean
  wfIdCopied: string | null
  onCopyWorkflowId: (id: string) => Promise<void>
  onSelect?: () => void
  onSelectEntry?: (entry: HistoryEntry) => void
  isMobile?: boolean
  onToggle?: () => void
  onCancel?: () => void | Promise<void>
  onResume?: (entry: HistoryEntry) => void
  onArchive?: (workflowId: string, topic?: string) => void
  onMoveToCompleted?: (workflowId: string) => void
  onMoveToInProgress?: (workflowId: string) => void
  onDelete?: (workflowId: string) => void
  /** A lane move for this card is in flight. */
  busy?: boolean
  noteValue?: string
  noteFlashKey?: number
  onNoteChange?: (value: string) => void
}

/** Time of day only; the status row already shows the date. */
function formatCreatedMeta(raw: string): string | null {
  const parsed = new Date(raw.includes("T") ? raw : `${raw.replace(" ", "T")}Z`)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
}

const iconButton =
  "relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-control transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

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
  onResume,
  onArchive,
  onMoveToCompleted,
  onMoveToInProgress,
  onDelete,
  busy = false,
  noteValue = "",
  noteFlashKey = 0,
  onNoteChange,
}: RunNavCardProps) {
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [noteOpen, setNoteOpen] = useState(false)
  const focusNoteOnMenuClose = useRef(false)
  const noteWrapRef = useRef<HTMLDivElement>(null)
  const detailsId = useId()
  const disabledReasonId = useId()

  const workflowId = model.workflowId
  const entry = model.entry
  const isLive = model.variant === "live"
  const isLane = model.variant === "completed" || model.variant === "archived"
  const selectable = isLive || isLane || model.canOpen
  const disabledReason = selectable ? undefined : (model.disabledReason ?? "Not available yet")

  const handleSelect = () => {
    if (!selectable) return
    if (isLive) {
      onSelect?.()
      if (isMobile) onToggle?.()
      return
    }
    if (entry) onSelectEntry?.(entry)
  }

  const isNow = model.dateLabel === "Now"
  const dateText = isNow ? "Now" : model.dateLabel ? formatShortDate(model.dateLabel) : undefined
  const dateTitle = !isNow && model.dateLabel ? formatRunDate(model.dateLabel) : undefined

  const statusLabel = model.statusLabel
  const metaParts = [
    workflowId ? formatWorkflowId(workflowId) : null,
    !isNow && model.dateLabel ? formatCreatedMeta(model.dateLabel) : null,
  ].filter(Boolean)
  const metaText = metaParts.length > 0 ? metaParts.join(" · ") : null

  if (collapsed) {
    return (
      <SidebarTooltip
        label={disabledReason ? `${model.topic} (${disabledReason})` : model.topic}
        collapsed
        side="right"
      >
        <button
          type="button"
          onClick={handleSelect}
          aria-disabled={!selectable || undefined}
          aria-current={model.isSelected ? "page" : undefined}
          aria-label={`${model.topic}${statusLabel ? `, ${statusLabel}` : ""}`}
          className={cn(
            "flex h-9 w-9 mx-auto items-center justify-center rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            model.isSelected ? "sidebar-card-selected" : "hover:bg-surface-2/60",
            !selectable && "opacity-60 cursor-not-allowed",
          )}
        >
          <CollapsedWorkflowBadge workflowId={workflowId} status={model.statusKey} />
        </button>
      </SidebarTooltip>
    )
  }

  const showStop = Boolean(onCancel && model.rowIsRunning && (isLive || model.isLiveRow))
  const showResume = Boolean(model.isResumable && onResume && entry && !isLane)
  const canArchive = Boolean(onArchive && workflowId && !model.rowIsRunning && model.variant !== "archived")
  const canComplete = Boolean(
    onMoveToCompleted &&
      workflowId &&
      (model.variant === "archived" || (model.variant === "in-progress" && model.isCompletedLaneEligible)),
  )
  const canMoveToInProgress = Boolean(onMoveToInProgress && workflowId && isLane)
  const canDelete = Boolean(onDelete && workflowId && model.variant === "archived")
  const canAddNote = Boolean(
    model.showNoteField && entry && onNoteChange && noteValue.trim() === "" && !noteOpen,
  )
  const hasMenu = canArchive || canComplete || canMoveToInProgress || canDelete || canAddNote
  const showNote = Boolean(
    model.showNoteField && entry && onNoteChange && (noteValue.trim() !== "" || noteOpen),
  )
  const readOnlyNote = !showNote ? (entry?.notes ?? "").trim() : ""

  const metricInput = {
    papersFound: model.papersFound,
    papersIncluded: model.papersIncluded,
    funnelStages: model.funnelStages,
    cost: model.cost,
  }
  const keyMetric = keyMetricText(metricInput)
  const hasDetails = hasRunCardDetails(metricInput)

  return (
    <div
      className={cn(
        "sidebar-card relative",
        model.cardClassName,
        model.isSelected
          ? "sidebar-card-selected"
          : selectable
            ? "sidebar-card-hover"
            : "opacity-70",
      )}
    >
      <div className="flex items-start gap-2 pl-2.5 pr-1.5 pt-2">
        {model.showWorkflowBadge && (
          <ExpandedWorkflowBadge workflowId={workflowId} status={model.statusKey} />
        )}
        <Tooltip delayDuration={600}>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleSelect}
              aria-disabled={!selectable || undefined}
              aria-describedby={disabledReason ? disabledReasonId : undefined}
              aria-current={model.isSelected ? "page" : undefined}
              className={cn(
                "min-w-0 flex-1 pt-0.5 text-left text-xs leading-snug text-foreground",
                "after:absolute after:inset-0 after:rounded-xl after:content-['']",
                "focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-ring",
                !selectable && "cursor-not-allowed",
              )}
            >
              <span className="line-clamp-2">{model.topic}</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right" className="max-w-xs text-xs">
            {model.topic}
            {disabledReason && <span className="block text-muted">{disabledReason}</span>}
          </TooltipContent>
        </Tooltip>
        <div className="flex shrink-0 items-center gap-0.5">
          {showStop && (
            <button
              type="button"
              onClick={() => setStopConfirmOpen(true)}
              aria-label="Stop run"
              title="Stop run"
              className={cn(iconButton, "bg-intent-danger-solid text-intent-danger-solid-fg hover:bg-intent-danger-solid/85")}
            >
              <Square className="h-2.5 w-2.5 fill-current" aria-hidden />
            </button>
          )}
          {showResume && (
            <button
              type="button"
              onClick={() => onResume!(entry!)}
              disabled={model.isResuming}
              aria-label="Resume from last checkpoint"
              title="Resume from last checkpoint"
              className={cn(
                iconButton,
                "border border-intent-primary-border bg-intent-primary-subtle text-intent-primary hover:text-intent-primary-text",
                model.isResuming && "cursor-wait opacity-80",
              )}
            >
              {model.isResuming ? <Spinner size="xs" /> : <Play className="h-2.5 w-2.5 fill-current" aria-hidden />}
            </button>
          )}
          {hasMenu && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label="More actions"
                  disabled={busy}
                  className={cn(iconButton, "text-muted hover:bg-surface-2 hover:text-foreground data-[state=open]:bg-surface-2")}
                >
                  {busy ? <Spinner size="xs" /> : <MoreHorizontal className="h-3.5 w-3.5" aria-hidden />}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="bottom"
                align="end"
                sideOffset={4}
                collisionPadding={8}
                updatePositionStrategy="always"
                className="min-w-44"
                onCloseAutoFocus={(e) => {
                  if (!focusNoteOnMenuClose.current) return
                  focusNoteOnMenuClose.current = false
                  e.preventDefault()
                  requestAnimationFrame(() => noteWrapRef.current?.querySelector("textarea")?.focus())
                }}
              >
                {canAddNote && (
                  <DropdownMenuItem
                    onSelect={() => {
                      focusNoteOnMenuClose.current = true
                      setNoteOpen(true)
                    }}
                  >
                    <StickyNote aria-hidden />
                    Add note
                  </DropdownMenuItem>
                )}
                {canMoveToInProgress && (
                  <DropdownMenuItem onSelect={() => onMoveToInProgress!(workflowId!)}>
                    <Clock aria-hidden />
                    Move to In progress
                  </DropdownMenuItem>
                )}
                {canComplete && (
                  <DropdownMenuItem onSelect={() => onMoveToCompleted!(workflowId!)}>
                    <CheckSquare aria-hidden />
                    Move to Completed
                  </DropdownMenuItem>
                )}
                {canArchive && (
                  <DropdownMenuItem onSelect={() => onArchive!(workflowId!, model.topic)}>
                    <Archive aria-hidden />
                    Archive
                  </DropdownMenuItem>
                )}
                {canDelete && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem destructive onSelect={() => onDelete!(workflowId!)}>
                      <Trash2 aria-hidden />
                      Delete permanently…
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {metaText && (
        <p className="truncate px-2.5 pt-1 text-2xs tabular-nums text-muted">{metaText}</p>
      )}

      {readOnlyNote && (
        <p className="truncate px-2.5 pt-1 text-2xs italic text-muted" title={readOnlyNote}>
          {readOnlyNote}
        </p>
      )}

      {disabledReason && (
        <p id={disabledReasonId} className="px-2.5 pt-0.5 text-2xs text-muted">
          {disabledReason}
        </p>
      )}

      <div className="flex items-center justify-between gap-2 min-w-0 px-2.5 pt-1 pb-2 text-meta">
        <RunStatusIndicator
          status={model.statusKey}
          animate={model.animateStatus}
          loading={model.isOpening}
          label={statusLabel}
          className="min-w-0 shrink text-xs"
        />
        {dateText && (
          <time
            dateTime={isNow ? undefined : model.dateLabel}
            title={dateTitle}
            className={cn("font-medium tabular-nums shrink-0", model.dateClassName)}
          >
            {dateText}
          </time>
        )}
      </div>

      {hasDetails && (
        <div className="-mt-1 flex px-2.5 pb-2 text-meta">
          <RunCardDetailsToggle
            expanded={detailsOpen}
            onToggle={() => setDetailsOpen((v) => !v)}
            label={keyMetric}
            controlsId={detailsId}
          />
        </div>
      )}

      {detailsOpen && hasDetails && (
        <div className="px-2.5 pb-2">
          <RunCardDetails
            id={detailsId}
            {...metricInput}
            workflowId={workflowId}
            copiedWorkflowId={wfIdCopied}
            onCopyWorkflowId={onCopyWorkflowId}
          />
        </div>
      )}

      {model.showProgressBar && (
        <CardProgressBar status={model.statusKey} progress={model.progressValue} />
      )}

      {showNote && (
        <div
          ref={noteWrapRef}
          className="relative z-10"
          onBlur={(e) => {
            if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
            const textarea = e.currentTarget.querySelector("textarea")
            if (!textarea?.value.trim()) setNoteOpen(false)
          }}
        >
          <NoteField
            key={`note-${entry!.workflow_id}`}
            workflowId={entry!.workflow_id}
            value={noteValue}
            flashKey={noteFlashKey}
            onChange={onNoteChange!}
          />
        </div>
      )}

      {onCancel && (
        <ConfirmDialog
          open={stopConfirmOpen}
          onOpenChange={setStopConfirmOpen}
          title="Stop this run?"
          description="The run will be interrupted. Completed phases are saved, and you can resume it later from its last checkpoint."
          confirmLabel="Stop run"
          pendingLabel="Stopping..."
          cancelLabel="Keep running"
          onConfirm={() => onCancel()}
        />
      )}
    </div>
  )
}
