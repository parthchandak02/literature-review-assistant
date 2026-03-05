import { useCallback, useEffect, useRef, useState } from "react"
import {
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Clock,
  Play,
  Plus,
  RefreshCw,
  Square,
  Trash2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { formatRunDate, formatWorkflowId } from "@/lib/format"
import { fetchHistory } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog"
import {
  type RunStatus,
  STATUS_LABEL,
  STATUS_DOT,
  STATUS_TEXT,
  resolveRunStatus,
} from "@/lib/constants"

// Sidebar uses resolveRunStatus under its local alias for readability
const resolveStatus = resolveRunStatus

function fmtNum(n: number): string {
  return n.toLocaleString()
}

export interface PhaseProgress {
  value: number
  completedPhases: number
  currentPhaseFraction?: number
}

export interface LiveRun {
  runId: string
  topic: string
  status: RunStatus
  cost: number
  workflowId?: string | null
  phaseProgress?: PhaseProgress
  startedAt?: string | null
  papersFound?: number | null
  papersIncluded?: number | null
}

interface SidebarProps {
  liveRun: LiveRun | null
  /** workflowId of the historical run being viewed (null when viewing live run or setup). */
  selectedWorkflowId: string | null
  /** True when the live run is currently being viewed in the main area. */
  isLiveRunSelected: boolean
  onSelectLiveRun: () => void
  onSelectHistory: (entry: HistoryEntry) => void
  onNewReview: () => void
  onResume?: (entry: HistoryEntry) => Promise<void>
  onDelete?: (workflowId: string) => Promise<void>
  onCancel?: () => void
  isRunning?: boolean
  onGoHome?: () => void
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const PROGRESS_BAR_COLOR: Record<RunStatus, string> = {
  idle: "bg-zinc-600",
  connecting: "bg-violet-500",
  streaming: "bg-violet-500",
  done: "bg-emerald-500",
  error: "bg-red-500",
  cancelled: "bg-amber-500",
  stale: "bg-amber-600",
}

export function Sidebar({
  liveRun,
  selectedWorkflowId,
  isLiveRunSelected,
  onSelectLiveRun,
  onSelectHistory,
  onNewReview,
  onResume,
  onDelete,
  onCancel,
  isRunning: isRunningProp,
  onGoHome,
  collapsed,
  onToggle,
  width,
  onWidthChange,
}: SidebarProps) {
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [resumingId, setResumingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteConfirmWorkflowId, setDeleteConfirmWorkflowId] =
    useState<string | null>(null)
  const [wfIdCopied, setWfIdCopied] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    setHistoryError(null)
    try {
      const data = await fetchHistory()
      setHistory(data)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setHistoryError(
        msg.toLowerCase().includes("fetch") ? "Cannot reach backend" : msg,
      )
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // Fetch history on mount, poll every 15s (picks up in-progress CLI runs),
  // and whenever the live run finishes. Pause polling when tab is hidden.
  useEffect(() => {
    void loadHistory()
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void loadHistory()
    }, 15_000)
    return () => clearInterval(id)
  }, [loadHistory])

  useEffect(() => {
    if (
      liveRun?.status === "done" ||
      liveRun?.status === "error" ||
      liveRun?.status === "cancelled"
    ) {
      void loadHistory()
      // Second refresh after 3s: the registry write lags behind the SSE "done"
      // event, so the first call may still see the old status. The delayed
      // call catches the final persisted status (e.g. "completed").
      const timer = setTimeout(() => void loadHistory(), 3000)
      return () => clearTimeout(timer)
    }
  }, [liveRun?.status, loadHistory])

  // Drag-to-resize the sidebar
  useEffect(() => {
    if (!isDragging) return
    function onMouseMove(e: MouseEvent) {
      const delta = e.clientX - dragStartX.current
      const next = Math.max(200, Math.min(420, dragStartWidth.current + delta))
      onWidthChange(next)
    }
    function onMouseUp() {
      setIsDragging(false)
    }
    document.addEventListener("mousemove", onMouseMove)
    document.addEventListener("mouseup", onMouseUp)
    return () => {
      document.removeEventListener("mousemove", onMouseMove)
      document.removeEventListener("mouseup", onMouseUp)
    }
  }, [isDragging, onWidthChange])

  const isRunning =
    isRunningProp ?? (liveRun?.status === "streaming" || liveRun?.status === "connecting")

  async function handleSelectHistory(entry: HistoryEntry) {
    setOpeningId(entry.workflow_id)
    try {
      await onSelectHistory(entry)
    } finally {
      setOpeningId(null)
    }
  }

  function handleResumeClick(e: React.MouseEvent, entry: HistoryEntry) {
    e.stopPropagation()
    if (!onResume) return
    void handleResumeFromModal(entry)
  }

  async function handleResumeFromModal(entry: HistoryEntry) {
    if (!onResume) return
    setResumingId(entry.workflow_id)
    try {
      await onResume(entry)
    } finally {
      setResumingId(null)
    }
  }

  function handleDeleteClick(e: React.MouseEvent, workflowId: string) {
    e.stopPropagation()
    if (!onDelete) return
    setDeleteConfirmWorkflowId(workflowId)
  }

  async function handleDeleteConfirm(workflowId: string) {
    if (!onDelete) return
    setDeletingId(workflowId)
    try {
      await onDelete(workflowId)
      await loadHistory()
    } finally {
      setDeletingId(null)
    }
  }

  function handleDragHandleMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    dragStartX.current = e.clientX
    dragStartWidth.current = width
    setIsDragging(true)
  }

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          "fixed left-0 top-0 h-full bg-zinc-900 border-r border-zinc-800 flex flex-col z-20 select-none overflow-hidden",
          !isDragging && "transition-[width] duration-200 ease-in-out",
        )}
        style={{ width: collapsed ? 56 : width }}
      >
        {/* Logo row - clickable to go home */}
        <button
          type="button"
          onClick={() => onGoHome?.()}
          className={cn(
            "flex items-center h-14 border-b border-zinc-800 shrink-0 px-3.5 gap-2 w-full text-left",
            "hover:bg-zinc-800/50 transition-colors cursor-pointer",
          )}
        >
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-600 shrink-0">
            <BookMarked className="h-3.5 w-3.5 text-white" />
          </div>
          <div
            className={cn(
              "flex items-center gap-2 overflow-hidden transition-all duration-200",
              collapsed ? "w-0 opacity-0" : "w-auto opacity-100",
            )}
          >
            <span className="font-semibold text-sm text-white tracking-tight whitespace-nowrap">
              LitReview
            </span>
            <span className="text-[10px] font-medium text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded whitespace-nowrap">
              BETA
            </span>
          </div>
        </button>

        {/* New Review button */}
        <div className={cn("px-2.5 pt-3 pb-2 shrink-0", collapsed && "px-2")}>
          <SidebarTooltip label="New Review" collapsed={collapsed} side="right">
            <button
              onClick={onNewReview}
              className={cn(
                "flex items-center gap-2 rounded-lg transition-colors text-sm font-medium w-full",
                "bg-violet-600 hover:bg-violet-500 text-white",
                collapsed
                  ? "justify-center h-9 w-9 mx-auto"
                  : "px-3 py-2",
              )}
            >
              <Plus className="h-4 w-4 shrink-0" />
              {!collapsed && "New Review"}
            </button>
          </SidebarTooltip>
        </div>

        {/* Run list -- unified single "Runs" section */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 pb-2 pt-1">
          <section>
            {/* Section header */}
            {!collapsed && (
              <div className="flex items-center justify-between px-1 mb-1.5">
                <span className="label-caps font-semibold text-zinc-600">
                  Runs
                </span>
                <button
                  onClick={() => void loadHistory()}
                  disabled={loadingHistory}
                  aria-label="Refresh history"
                  className="text-zinc-600 hover:text-zinc-400 transition-colors"
                >
                  <RefreshCw
                    className={cn("h-3 w-3", loadingHistory && "animate-spin")}
                  />
                </button>
              </div>
            )}

            {historyError && !collapsed && (
              <div className="px-2 py-1.5 mb-2 rounded-md bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">
                {historyError}
              </div>
            )}

            {loadingHistory && history.length === 0 && !liveRun && !collapsed && (
              <div className="space-y-1">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="pl-2.5 pr-2 py-2.5 rounded-r-md border-l-2 border-zinc-700">
                    <div className="h-2.5 bg-zinc-800 rounded animate-pulse w-3/4 mb-1.5" />
                    <div className="h-2 bg-zinc-800 rounded animate-pulse w-1/2" />
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-1.5">
              {/* Live run card - first in the unified list, handles both collapsed and expanded */}
              {liveRun && (
                <SidebarTooltip label={liveRun.topic} collapsed={collapsed} side="right">
                  <div className={cn(
                    "rounded-r-md overflow-hidden",
                    !collapsed && "rounded-b-none",
                    isLiveRunSelected && "bg-zinc-800",
                  )}>
                    <div className="relative">
                      <button
                        onClick={onSelectLiveRun}
                        className={cn(
                          "w-full transition-colors text-left",
                          collapsed
                            ? "flex justify-center items-center h-9 w-9 mx-auto rounded-lg"
                            : "pl-2.5 pr-2 py-2.5",
                          isLiveRunSelected
                            ? "bg-zinc-800"
                            : "hover:bg-zinc-800/60",
                        )}
                      >
                        {collapsed ? (
                          <RunDot status={liveRun.status} animate={isRunning} />
                        ) : (
                          <div
                            className={cn(
                              "flex flex-col gap-1 min-w-0",
                              ((onDelete && liveRun.workflowId && !isRunning) || (isRunning && onCancel)) && "pr-12",
                            )}
                          >
                            <span className="text-xs text-zinc-300 line-clamp-2 leading-snug">
                              {liveRun.topic}
                            </span>
                            <RunCardMetrics
                              papersFound={liveRun.papersFound}
                              papersIncluded={liveRun.papersIncluded}
                              cost={liveRun.cost}
                              workflowId={liveRun.workflowId}
                              copiedWorkflowId={wfIdCopied}
                              onCopyWorkflowId={async (id) => {
                                if (id) {
                                  await navigator.clipboard.writeText(id)
                                  setWfIdCopied(id)
                                  setTimeout(() => setWfIdCopied(null), 1500)
                                }
                              }}
                            />
                            <div className="flex items-center gap-2 min-w-0 flex-wrap text-meta">
                              <div className="flex items-center gap-1.5 shrink-0">
                                <RunDot status={liveRun.status} animate={isRunning} />
                                <span
                                  className={cn(
                                    "font-semibold uppercase tracking-wide",
                                    STATUS_TEXT[liveRun.status],
                                  )}
                                >
                                  {STATUS_LABEL[liveRun.status]}
                                </span>
                              </div>
                              <span className="text-white font-medium tabular-nums">
                                {liveRun.startedAt ? formatRunDate(liveRun.startedAt) : "Now"}
                              </span>
                            </div>
                          </div>
                        )}
                      </button>
                      {!collapsed && isRunning && onCancel && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onCancel()
                          }}
                          aria-label="Stop run"
                          title="Stop run"
                          className="absolute top-1.5 right-1.5 flex items-center justify-center h-5 w-5 rounded bg-red-600 hover:bg-red-500 text-white transition-colors"
                        >
                          <Square className="h-2.5 w-2.5 fill-white" />
                        </button>
                      )}
                      {!collapsed && onDelete && liveRun.workflowId && !isRunning && (
                        <button
                          onClick={(e) => handleDeleteClick(e, liveRun.workflowId!)}
                          disabled={deletingId === liveRun.workflowId}
                          aria-label="Delete run"
                          title="Delete run"
                          className={cn(
                            "absolute top-1.5 right-1.5 flex items-center justify-center h-5 w-5 rounded",
                            "text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors",
                            deletingId === liveRun.workflowId && "opacity-50 cursor-wait",
                          )}
                        >
                          {deletingId === liveRun.workflowId ? (
                            <div className="h-2.5 w-2.5 border border-zinc-500 border-t-zinc-300 rounded-full animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </button>
                      )}
                    </div>
                    {!collapsed && (
                      <CardProgressBar
                        status={liveRun.status}
                        progress={liveRun.phaseProgress?.value}
                      />
                    )}
                  </div>
                </SidebarTooltip>
              )}
              {(liveRun?.workflowId
                ? history.filter((e) => e.workflow_id !== liveRun.workflowId)
                // workflowId is null during the connecting window (before workflow_id_ready
                // fires). Filter by live_run_id to prevent the active run appearing twice.
                : liveRun?.runId
                  ? history.filter((e) => e.live_run_id !== liveRun.runId)
                  : history
              ).map((entry) => {
                const statusKey = resolveStatus(entry.status)
                const isSelected = selectedWorkflowId === entry.workflow_id
                const isOpening = openingId === entry.workflow_id
                const canOpen = Boolean(entry.db_path)

                // Metadata in run info strip order: Status, Time, Found, Included, Cost, WF ID (omit "out")

                // Entries with live_run_id are actively running in-process -- clicking
                // the card connects live SSE. They do NOT need a Resume button.
                const isResumable = onResume !== undefined &&
                  !entry.live_run_id &&
                  ["streaming", "cancelled", "error", "stale"].includes(statusKey)
                const isResuming = resumingId === entry.workflow_id

                const progressValue = statusKey === "done" ? 1 : entry.live_run_id ? -1 : undefined

                return (
                  <SidebarTooltip
                    key={entry.workflow_id}
                    label={entry.topic}
                    collapsed={collapsed}
                    side="right"
                  >
                    <div className={cn(
                      "rounded-r-md overflow-hidden",
                      !collapsed && "rounded-b-none",
                      isSelected && "bg-zinc-800",
                    )}>
                      <div className="relative">
                        <button
                          onClick={() => canOpen && void handleSelectHistory(entry)}
                          disabled={!canOpen}
                          className={cn(
                            "w-full transition-colors text-left",
                            collapsed
                              ? "flex justify-center items-center h-9 w-9 mx-auto rounded-lg"
                              : "pl-2.5 pr-2 py-2.5",
                            isSelected
                              ? "bg-zinc-800"
                              : canOpen
                                ? "hover:bg-zinc-800/50"
                                : "opacity-40 cursor-not-allowed",
                          )}
                        >
                          {collapsed ? (
                            <RunDot status={statusKey} />
                          ) : (
                            <div
                              className={cn(
                                "flex flex-col gap-1 min-w-0",
                                (onDelete || isResumable) && "pr-12",
                              )}
                            >
                              <span className="text-xs text-zinc-300 line-clamp-2 leading-snug">
                                {entry.topic}
                              </span>
                              <RunCardMetrics
                                papersFound={entry.papers_found}
                                papersIncluded={entry.papers_included}
                                cost={entry.total_cost}
                                workflowId={entry.workflow_id}
                                copiedWorkflowId={wfIdCopied}
                                onCopyWorkflowId={async (id) => {
                                  if (id) {
                                    await navigator.clipboard.writeText(id)
                                    setWfIdCopied(id)
                                    setTimeout(() => setWfIdCopied(null), 1500)
                                  }
                                }}
                              />
                              <div className="flex items-center gap-2 min-w-0 flex-wrap text-meta">
                                <div className="flex items-center gap-1.5 shrink-0">
                                  {isOpening ? (
                                    <div className="h-1.5 w-1.5 rounded-full border border-zinc-500 animate-spin" />
                                  ) : (
                                    <RunDot status={statusKey} />
                                  )}
                                  <span
                                    className={cn(
                                      "font-semibold uppercase tracking-wide",
                                      STATUS_TEXT[statusKey],
                                    )}
                                  >
                                    {STATUS_LABEL[statusKey]}
                                  </span>
                                </div>
                                {entry.created_at && (
                                  <span className="text-white font-medium tabular-nums">
                                    {formatRunDate(entry.created_at)}
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </button>

                        {/* Action buttons: trash (all) + resume (resumable only) */}
                        {!collapsed && (
                          <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
                            {onDelete && (
                              <button
                                onClick={(e) => handleDeleteClick(e, entry.workflow_id)}
                                disabled={deletingId === entry.workflow_id}
                                aria-label="Delete run"
                                title="Delete run"
                                className={cn(
                                  "flex items-center justify-center h-5 w-5 rounded",
                                  "text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-colors",
                                  deletingId === entry.workflow_id && "opacity-50 cursor-wait",
                                )}
                              >
                                {deletingId === entry.workflow_id ? (
                                  <div className="h-2.5 w-2.5 border border-zinc-500 border-t-zinc-300 rounded-full animate-spin" />
                                ) : (
                                  <Trash2 className="h-3 w-3" />
                                )}
                              </button>
                            )}
                            {isResumable && (
                              <button
                                onClick={(e) => handleResumeClick(e, entry)}
                                disabled={isResuming}
                                aria-label="Resume run"
                                title="Resume run"
                                className={cn(
                                  "flex items-center justify-center h-5 w-5 rounded bg-violet-600 hover:bg-violet-500 text-white",
                                  isResuming && "opacity-80 cursor-wait",
                                )}
                              >
                                {isResuming ? (
                                  <div className="h-2.5 w-2.5 border border-white/60 border-t-white rounded-full animate-spin" />
                                ) : (
                                  <Play className="h-2.5 w-2.5 fill-white" />
                                )}
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                      {!collapsed && (
                        <CardProgressBar status={statusKey} progress={progressValue} />
                      )}
                    </div>
                  </SidebarTooltip>
                )
              })}
            </div>

            {!collapsed && !loadingHistory && (
              liveRun?.workflowId
                ? history.filter((e) => e.workflow_id !== liveRun.workflowId).length === 0
                : liveRun?.runId
                  ? history.filter((e) => e.live_run_id !== liveRun.runId).length === 0
                  : history.length === 0
            ) && (
              <div className="flex flex-col items-center py-6 gap-2">
                <Clock className="h-6 w-6 text-zinc-700" />
                <p className="label-muted text-center">
                  Past reviews will appear here automatically.
                </p>
              </div>
            )}
          </section>
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex items-center justify-center h-9 shrink-0 border-t border-zinc-800",
            "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors",
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>

        {/* Drag resize handle */}
        {!collapsed && (
          <div
            onMouseDown={handleDragHandleMouseDown}
            className={cn(
              "absolute top-0 right-0 w-1 h-full cursor-col-resize z-30",
              "hover:bg-violet-500/40 transition-colors duration-150",
              isDragging && "bg-violet-500/60",
            )}
          />
        )}
      </aside>

      {onDelete && (
        <DeleteConfirmDialog
          open={deleteConfirmWorkflowId !== null}
          onOpenChange={(open) => !open && setDeleteConfirmWorkflowId(null)}
          workflowId={deleteConfirmWorkflowId}
          onConfirm={handleDeleteConfirm}
        />
      )}
    </TooltipProvider>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function RunCardMetrics({
  papersFound,
  papersIncluded,
  cost,
  workflowId,
  copiedWorkflowId,
  onCopyWorkflowId,
}: {
  papersFound?: number | null
  papersIncluded?: number | null
  cost?: number | null
  workflowId?: string | null
  copiedWorkflowId?: string | null
  onCopyWorkflowId?: (id: string) => void | Promise<void>
}) {
  const hasStats =
    papersFound != null ||
    papersIncluded != null ||
    (cost != null && cost > 0)
  const hasWfId = workflowId != null && workflowId.length > 0

  if (!hasStats && !hasWfId) return null

  return (
    <div className="flex items-baseline justify-between gap-x-3 min-w-0 text-meta">
      {hasStats && (
        <div className="flex items-baseline gap-x-3 flex-wrap gap-y-0.5 min-w-0">
        {papersFound != null && (
          <span className="flex items-baseline gap-0.5 leading-none shrink-0">
            <span className="font-semibold text-blue-400">{fmtNum(papersFound)}</span>
            <span className="text-zinc-600 font-normal">found</span>
          </span>
        )}
        {papersIncluded != null && (
          <span className="flex items-baseline gap-0.5 leading-none shrink-0">
            <span className="font-semibold text-emerald-400">{fmtNum(papersIncluded)}</span>
            <span className="text-zinc-600 font-normal">included</span>
          </span>
        )}
        {cost != null && cost > 0 && (
          <span className="font-semibold text-amber-400 shrink-0">
            ${cost.toFixed(3)}
          </span>
        )}
        </div>
      )}
      {hasWfId && (
        onCopyWorkflowId ? (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation()
              void onCopyWorkflowId(workflowId!)
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.stopPropagation()
                void onCopyWorkflowId(workflowId!)
              }
            }}
            className={cn(
              "text-zinc-600 shrink-0 whitespace-nowrap hover:text-zinc-400 transition-colors cursor-pointer",
              !hasStats && "ml-auto",
            )}
            title="Copy workflow ID"
          >
            {copiedWorkflowId === workflowId ? "Copied!" : formatWorkflowId(workflowId!)}
          </span>
        ) : (
          <span
            className={cn(
              "text-zinc-600 shrink-0 whitespace-nowrap",
              !hasStats && "ml-auto",
            )}
            title={workflowId ?? undefined}
          >
            {formatWorkflowId(workflowId!)}
          </span>
        )
      )}
    </div>
  )
}

function CardProgressBar({
  status,
  progress,
}: {
  status: RunStatus
  progress?: number
}) {
  const colorClass = PROGRESS_BAR_COLOR[status] ?? "bg-zinc-600"
  // progress === -1 is the indeterminate sentinel: active background run with no live SSE data
  const isIndeterminate = progress === -1
  const showFill =
    !isIndeterminate &&
    (status === "streaming" || status === "connecting" || status === "done")
  const fillPercent = showFill ? (progress != null ? progress * 100 : status === "done" ? 100 : 0) : 0

  if (isIndeterminate) {
    return (
      <div className="h-1 rounded-b-md overflow-hidden bg-zinc-800">
        <div className="h-full w-1/3 rounded-full bg-violet-500/60 animate-pulse" />
      </div>
    )
  }

  return (
    <div
      className={cn(
        "h-1 rounded-b-md overflow-hidden",
        showFill ? "bg-zinc-800" : colorClass,
      )}
    >
      {showFill && (
        <div
          className={cn("h-full transition-all duration-300", colorClass)}
          style={{ width: `${fillPercent}%` }}
        />
      )}
    </div>
  )
}

function RunDot({
  status,
  animate = false,
}: {
  status: RunStatus | "idle"
  animate?: boolean
}) {
  const color = STATUS_DOT[status] ?? "bg-zinc-600"
  if (animate) {
    return (
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        <span
          className={cn(
            "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
            color,
          )}
        />
        <span className={cn("relative inline-flex rounded-full h-1.5 w-1.5", color)} />
      </span>
    )
  }
  return <span className={cn("inline-flex rounded-full h-1.5 w-1.5 shrink-0", color)} />
}

function SidebarTooltip({
  label,
  collapsed,
  side,
  children,
}: {
  label: string
  collapsed: boolean
  side?: "right" | "left" | "top" | "bottom"
  children: React.ReactNode
}) {
  if (!collapsed) return <>{children}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        side={side ?? "right"}
        className="bg-zinc-800 border-zinc-700 text-zinc-200 text-xs max-w-[200px]"
      >
        {label}
      </TooltipContent>
    </Tooltip>
  )
}
