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
import { fetchHistory, saveNote } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import type { FunnelStage } from "@/lib/funnelStages"
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
  funnelStages?: FunnelStage[]
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
  onResume?: (entry: HistoryEntry, fromPhase?: string | null) => Promise<void>
  onDelete?: (workflowId: string) => Promise<void>
  onCancel?: () => void
  isRunning?: boolean
  onGoHome?: () => void
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
  /** When true, renders the sidebar as a slide-in overlay drawer instead of a fixed column. */
  isMobile?: boolean
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
  isMobile = false,
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

  // Notes: keyed by workflow_id. Seeded from history, updated via SSE.
  const [notes, setNotes] = useState<Record<string, string>>({})
  // Flash counter per workflow_id: incrementing forces NoteField to re-key and retrigger
  // the animation even when the same card receives rapid successive remote updates.
  const [noteFlashCounters, setNoteFlashCounters] = useState<Record<string, number>>({})

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    setHistoryError(null)
    try {
      const data = await fetchHistory()
      setHistory(data)
      // Seed notes map from history response (server is source of truth on load).
      setNotes((prev) => {
        const next = { ...prev }
        for (const entry of data) {
          if (entry.notes != null) next[entry.workflow_id] = entry.notes
        }
        return next
      })
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setHistoryError(
        msg.toLowerCase().includes("fetch") ? "Cannot reach backend" : msg,
      )
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // Subscribe to the global notes SSE stream for real-time cross-client sync.
  useEffect(() => {
    const es = new EventSource("/api/notes/stream")
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string) as {
          workflow_id: string
          note: string
        }
        setNotes((prev) => ({ ...prev, [data.workflow_id]: data.note }))
        // Increment flash counter for the updated workflow so NoteField re-keys
        // and restarts the CSS animation even on rapid successive updates.
        setNoteFlashCounters((prev) => ({
          ...prev,
          [data.workflow_id]: (prev[data.workflow_id] ?? 0) + 1,
        }))
      } catch {
        // Ignore malformed events.
      }
    }
    es.onerror = () => {
      // EventSource auto-reconnects after errors; no manual action needed.
      // Errors in development (e.g. server restart) resolve on reconnect.
    }
    return () => es.close()
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

  const liveRunHasHistoryRow = Boolean(
    liveRun && history.some((entry) => {
      if (liveRun.workflowId && entry.workflow_id === liveRun.workflowId) return true
      return Boolean(entry.live_run_id && entry.live_run_id === liveRun.runId)
    }),
  )
  // Render a standalone live card only during the brief bootstrap window where
  // the active run is not yet present in /api/history. Once present, decorate
  // that stable history row in-place to avoid sidebar reshuffles.
  const shouldShowStandaloneLiveCard = Boolean(liveRun && !liveRunHasHistoryRow)

  async function handleSelectHistory(entry: HistoryEntry) {
    setOpeningId(entry.workflow_id)
    // Close the mobile drawer when a run is selected
    if (isMobile) onToggle()
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

  async function handleResumeFromModal(entry: HistoryEntry, fromPhase?: string | null) {
    if (!onResume) return
    setResumingId(entry.workflow_id)
    try {
      await onResume(entry, fromPhase)
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
      {/* Backdrop: only shown on mobile when the drawer is open */}
      {isMobile && !collapsed && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
          onClick={onToggle}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-0 h-full bg-zinc-950/90 border-r border-zinc-800/80 backdrop-blur-sm flex flex-col select-none overflow-hidden",
          isMobile
            ? cn(
                "z-50 w-72 transition-transform duration-200 ease-in-out",
                collapsed ? "-translate-x-full" : "translate-x-0",
              )
            : cn(
                "z-20",
                !isDragging && "transition-[width] duration-200 ease-in-out",
              ),
        )}
        style={isMobile
          ? { paddingTop: 'env(safe-area-inset-top)' }
          : { width: collapsed ? 56 : width, paddingTop: 'env(safe-area-inset-top)' }}
      >
        {/* Ambient violet glow -- gives the glass cards something to "float" against */}
        <div
          className="pointer-events-none absolute inset-0 z-0"
          aria-hidden
          style={{
            background: "radial-gradient(ellipse 80% 60% at 50% 110%, rgba(139,92,246,0.10) 0%, transparent 70%)",
          }}
        />

        {/* Logo row - clickable to go home */}
        <button
          type="button"
          onClick={() => { onGoHome?.(); if (isMobile) onToggle() }}
          className={cn(
            "relative z-10 flex items-center h-14 glass-toolbar border-b border-zinc-800/70 shrink-0 px-3.5 gap-2 w-full text-left",
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
          </div>
        </button>

        {/* New Review button */}
        <div className={cn("relative z-10 px-2.5 pt-3 pb-2 shrink-0", collapsed && "px-2")}>
          <SidebarTooltip label="New Review" collapsed={collapsed} side="right">
            <button
              onClick={() => { onNewReview(); if (isMobile) onToggle() }}
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
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 pb-2 pt-1 relative z-10">
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
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="sidebar-card px-3 py-3">
                    <div className="h-2.5 bg-zinc-700/50 rounded animate-pulse w-3/4 mb-2" />
                    <div className="h-2 bg-zinc-700/50 rounded animate-pulse w-1/2" />
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-2">
              {/* Live run card - first in the unified list, handles both collapsed and expanded */}
              {shouldShowStandaloneLiveCard && liveRun && (
                <SidebarTooltip label={liveRun.topic} collapsed={collapsed} side="right">
                  <div className={cn(
                    "sidebar-card",
                    isLiveRunSelected ? "sidebar-card-selected" : "sidebar-card-hover",
                  )}>
                    <div className="relative">
                      <button
                        onClick={() => { onSelectLiveRun(); if (isMobile) onToggle() }}
                        className={cn(
                          "w-full transition-colors text-left",
                          collapsed
                            ? "flex justify-center items-center h-9 w-9 mx-auto rounded-xl"
                            : "pl-2.5 pr-2 py-2.5",
                        )}
                      >
                        {collapsed ? (
                          <RunDot status={liveRun.status} animate={isRunning} />
                        ) : (
                          <div className="flex flex-col gap-1 min-w-0">
                            <span
                              className={cn(
                                "text-xs text-zinc-300 line-clamp-2 leading-snug",
                                ((onDelete && liveRun.workflowId && !isRunning) || (isRunning && onCancel)) && "pr-12",
                              )}
                            >
                              {liveRun.topic}
                            </span>
                            <RunCardMetrics
                              papersFound={liveRun.papersFound}
                              papersIncluded={liveRun.papersIncluded}
                              funnelStages={liveRun.funnelStages}
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
                            <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
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
                              <span className="text-zinc-400 font-medium tabular-nums shrink-0">
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
                          className="absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md bg-red-600 hover:bg-red-500 text-white transition-colors"
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
                            "absolute top-0 right-0 flex items-center justify-center h-8 w-8 rounded-bl-md",
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
              {history.map((entry) => {
                const isLiveRow = Boolean(
                  liveRun && (
                    (entry.live_run_id && entry.live_run_id === liveRun.runId) ||
                    (liveRun.workflowId && entry.workflow_id === liveRun.workflowId)
                  ),
                )
                const statusKey = isLiveRow && liveRun ? liveRun.status : resolveStatus(entry.status)
                const isSelected = selectedWorkflowId === entry.workflow_id
                const isOpening = openingId === entry.workflow_id
                const canOpen = Boolean(entry.db_path)
                const rowIsRunning = isLiveRow
                  ? statusKey === "streaming" || statusKey === "connecting"
                  : Boolean(entry.live_run_id)
                // Metadata in run info strip order: Status, Time, Found, Included, Cost, WF ID (omit "out")

                // Entries with live_run_id are actively running in-process -- clicking
                // the card connects live SSE. They do NOT need a Resume button.
                const isResumable = onResume !== undefined &&
                  !entry.live_run_id &&
                  ["streaming", "cancelled", "error", "stale"].includes(statusKey)
                const isResuming = resumingId === entry.workflow_id

                const progressValue = isLiveRow && liveRun
                  ? (liveRun.phaseProgress?.value ?? (rowIsRunning ? -1 : undefined))
                  : statusKey === "done"
                    ? 1
                    : entry.live_run_id
                      ? -1
                      : undefined

                return (
                  <SidebarTooltip
                    key={entry.workflow_id}
                    label={entry.topic}
                    collapsed={collapsed}
                    side="right"
                  >
                    <div className={cn(
                      "sidebar-card",
                      isSelected
                        ? "sidebar-card-selected"
                        : canOpen
                          ? "sidebar-card-hover"
                          : "opacity-50",
                    )}>
                      <div className="relative">
                        <button
                          onClick={() => canOpen && void handleSelectHistory(entry)}
                          disabled={!canOpen}
                          className={cn(
                            "w-full transition-colors text-left",
                            collapsed
                              ? "flex justify-center items-center h-9 w-9 mx-auto rounded-xl"
                              : "pl-2.5 pr-2 py-2.5",
                            !canOpen && "cursor-not-allowed",
                          )}
                        >
                          {collapsed ? (
                            <RunDot status={statusKey} />
                          ) : (
                            <div className="flex flex-col gap-1 min-w-0">
                              <span
                                className={cn(
                                  "text-xs text-zinc-300 line-clamp-2 leading-snug",
                                  (onDelete || isResumable) && "pr-12",
                                )}
                              >
                                {entry.topic}
                              </span>
                              <RunCardMetrics
                                papersFound={isLiveRow && liveRun ? (liveRun.papersFound ?? entry.papers_found) : entry.papers_found}
                                papersIncluded={isLiveRow && liveRun ? (liveRun.papersIncluded ?? entry.papers_included) : entry.papers_included}
                                funnelStages={isLiveRow && liveRun ? liveRun.funnelStages : undefined}
                                cost={isLiveRow && liveRun ? liveRun.cost : entry.total_cost}
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
                              <div className="flex items-center justify-between gap-2 min-w-0 text-meta">
                                <div className="flex items-center gap-1.5 shrink-0">
                                  {isOpening ? (
                                    <div className="h-1.5 w-1.5 rounded-full border border-zinc-500 animate-spin" />
                                  ) : (
                                    <RunDot status={statusKey} animate={rowIsRunning} />
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
                                  <span className="text-zinc-400 font-medium tabular-nums shrink-0">
                                    {formatRunDate(entry.created_at)}
                                  </span>
                                )}
                              </div>
                            </div>
                          )}
                        </button>

                        {/* Action buttons: trash (all) + resume (resumable only) */}
                        {!collapsed && (
                          <div className="absolute top-0 right-0 flex items-center">
                            {isLiveRow && rowIsRunning && onCancel && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onCancel()
                                }}
                                aria-label="Stop run"
                                title="Stop run"
                                className={cn(
                                  "flex items-center justify-center h-8 w-8 bg-red-600 hover:bg-red-500 text-white",
                                  (onDelete || isResumable) ? "" : "rounded-bl-md",
                                )}
                              >
                                <Square className="h-2.5 w-2.5 fill-white" />
                              </button>
                            )}
                            {onDelete && (
                              <button
                                onClick={(e) => handleDeleteClick(e, entry.workflow_id)}
                                disabled={deletingId === entry.workflow_id}
                                aria-label="Delete run"
                                title="Delete run"
                                className={cn(
                                  "flex items-center justify-center h-8 w-8",
                                  isResumable ? "" : "rounded-bl-md",
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
                                  "flex items-center justify-center h-8 w-8 rounded-bl-md bg-violet-600 hover:bg-violet-500 text-white",
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
                      {!collapsed && (
                        <NoteField
                          key={`note-${entry.workflow_id}`}
                          workflowId={entry.workflow_id}
                          value={notes[entry.workflow_id] ?? ""}
                          flashKey={noteFlashCounters[entry.workflow_id] ?? 0}
                          onChange={(val) =>
                            setNotes((prev) => ({ ...prev, [entry.workflow_id]: val }))
                          }
                        />
                      )}
                    </div>
                  </SidebarTooltip>
                )
              })}
            </div>

            {!collapsed && !loadingHistory && history.length === 0 && !shouldShowStandaloneLiveCard && (
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
            "relative z-10 flex items-center justify-center h-9 shrink-0 border-t border-zinc-800",
            "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors",
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>

        {/* Drag resize handle -- desktop only */}
        {!collapsed && !isMobile && (
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
  funnelStages,
  cost,
  workflowId,
  copiedWorkflowId,
  onCopyWorkflowId,
}: {
  papersFound?: number | null
  papersIncluded?: number | null
  funnelStages?: FunnelStage[]
  cost?: number | null
  workflowId?: string | null
  copiedWorkflowId?: string | null
  onCopyWorkflowId?: (id: string) => void | Promise<void>
}) {
  const hasFunnel = funnelStages != null && funnelStages.length > 0
  const hasStats =
    hasFunnel ||
    papersFound != null ||
    papersIncluded != null ||
    (cost != null && cost > 0)
  const hasWfId = workflowId != null && workflowId.length > 0

  if (!hasStats && !hasWfId) return null

  // 2-column layout:
  //   Left  -- funnel stages stacked vertically (or simple found/included rows)
  //   Right -- cost + workflow ID, right-aligned
  // Vertical stacking eliminates the need for inline arrows; order implies the flow.
  return (
    <div className="flex justify-between items-start gap-x-2 min-w-0 text-meta w-full">
      {/* Left column: pipeline stages */}
      <div className="flex flex-col gap-y-0.5 min-w-0">
        {hasFunnel ? (
          funnelStages!.map((stage) => (
            <span key={stage.key} className="flex items-baseline gap-1 leading-none">
              <span className={cn("font-semibold tabular-nums", stage.colorClass)}>
                {fmtNum(stage.count)}
              </span>
              <span className="text-zinc-600 font-normal">{stage.label}</span>
            </span>
          ))
        ) : (
          <>
            {papersFound != null && (
              <span className="flex items-baseline gap-1 leading-none">
                <span className="font-semibold tabular-nums text-blue-400">{fmtNum(papersFound)}</span>
                <span className="text-zinc-600 font-normal">found</span>
              </span>
            )}
            {papersIncluded != null && (
              <span className="flex items-baseline gap-1 leading-none">
                <span className="font-semibold tabular-nums text-emerald-400">{fmtNum(papersIncluded)}</span>
                <span className="text-zinc-600 font-normal">included</span>
              </span>
            )}
          </>
        )}
      </div>

      {/* Right column: cost + wf ID, right-aligned */}
      <div className="flex flex-col items-end gap-y-0.5 shrink-0">
        {cost != null && cost > 0 && (
          <span className="font-semibold text-amber-400 whitespace-nowrap">
            ${cost.toFixed(3)}
          </span>
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
              className="text-zinc-600 whitespace-nowrap hover:text-zinc-400 transition-colors cursor-pointer"
              title="Copy workflow ID"
            >
              {copiedWorkflowId === workflowId ? "Copied!" : formatWorkflowId(workflowId!)}
            </span>
          ) : (
            <span
              className="text-zinc-600 whitespace-nowrap"
              title={workflowId ?? undefined}
            >
              {formatWorkflowId(workflowId!)}
            </span>
          )
        )}
      </div>
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
      <div className="h-0.5 overflow-hidden bg-zinc-700/40">
        <div className="h-full w-1/3 rounded-full bg-violet-500/70 animate-pulse" />
      </div>
    )
  }

  return (
    <div
      className={cn(
        "h-0.5 overflow-hidden",
        showFill ? "bg-zinc-700/40" : colorClass,
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

// ---------------------------------------------------------------------------
// NoteField: inline per-workflow annotation with debounced autosave + flash
// ---------------------------------------------------------------------------

function NoteField({
  workflowId,
  value,
  flashKey,
  onChange,
}: {
  workflowId: string
  value: string
  /** Incremented by the parent each time a remote SSE update arrives.
   *  The component stays mounted (stable key); this prop drives an imperative
   *  CSS animation retrigger on the wrapper div without touching the textarea. */
  flashKey: number
  onChange: (val: string) => void
}) {
  const [localValue, setLocalValue] = useState(value)
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle")
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // Auto-grow helper: called both on user input and on programmatic value changes.
  function recalcHeight() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    // Allow up to 6 lines (~144px at 1.4 line-height with 11px font).
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  // Sync incoming value from server (SSE or history load) only when the
  // textarea is NOT focused -- never overwrite an in-progress local edit.
  // setState inside this effect is intentional: this IS the external system
  // (server-pushed value) driving local React state, which is the documented
  // use-case for useEffect + setState in React controlled-input patterns.
  useEffect(() => {
    if (document.activeElement !== textareaRef.current) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocalValue(value)
    }
  }, [value])

  // Recalculate height whenever localValue changes (covers programmatic updates).
  useEffect(() => {
    recalcHeight()
  }, [localValue])

  // Retrigger the amber flash animation imperatively on the wrapper div.
  // This avoids remounting the component (which would lose focus) while still
  // restarting the CSS animation for each incoming remote update.
  // Pattern: remove class -> force reflow -> re-add class (CSS-Tricks standard).
  useEffect(() => {
    if (flashKey === 0) return
    const el = wrapperRef.current
    if (!el) return
    el.classList.remove("animate-note-flash")
    void el.offsetWidth  // force reflow
    el.classList.add("animate-note-flash")
    const t = setTimeout(() => el.classList.remove("animate-note-flash"), 750)
    return () => clearTimeout(t)
  }, [flashKey])

  function scheduleSave(val: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    setSaveState("saving")
    debounceRef.current = setTimeout(() => {
      void persistNote(val)
    }, 500)
  }

  async function persistNote(val: string) {
    try {
      await saveNote(workflowId, val)
      setSaveState("saved")
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
      savedTimerRef.current = setTimeout(() => setSaveState("idle"), 1500)
    } catch {
      setSaveState("idle")
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value
    setLocalValue(val)
    onChange(val)
    scheduleSave(val)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Stop card click/select from bubbling up.
    e.stopPropagation()
    // Enter alone = save + blur (Slack-style). Shift+Enter = newline (default).
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      void persistNote(localValue)
      textareaRef.current?.blur()
    }
    // Escape = discard pending and blur.
    if (e.key === "Escape") {
      e.preventDefault()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      textareaRef.current?.blur()
    }
  }

  function handleBlur() {
    // Flush any pending debounce immediately on blur so edits are never lost.
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
      debounceRef.current = null
      void persistNote(localValue)
    }
  }

  return (
    <div
      ref={wrapperRef}
      className="mx-2 my-1 px-2 py-1 rounded"
      onClick={(e) => e.stopPropagation()}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={localValue}
        onChange={handleChange}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
        placeholder="Add a note..."
        className={cn(
          "w-full bg-transparent resize-none text-[11px] leading-relaxed",
          "text-amber-300/90 placeholder-zinc-600",
          "border-none outline-none focus:outline-none",
          "scrollbar-none block",
        )}
        style={{ minHeight: "1.4rem", overflowY: "hidden" }}
      />
      {saveState !== "idle" && (
        <span className="text-[10px] text-zinc-600 tabular-nums">
          {saveState === "saving" ? "Saving..." : "Saved"}
        </span>
      )}
    </div>
  )
}
