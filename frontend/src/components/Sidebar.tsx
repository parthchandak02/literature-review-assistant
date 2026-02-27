import { useCallback, useEffect, useRef, useState } from "react"
import {
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Clock,
  Play,
  Plus,
  RefreshCw,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { formatShortDate, formatWorkflowId } from "@/lib/format"
import { fetchHistory } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import {
  type RunStatus,
  STATUS_LABEL,
  STATUS_DOT,
  STATUS_TEXT,
  STATUS_BORDER,
  resolveRunStatus,
} from "@/lib/constants"

// Sidebar uses resolveRunStatus under its local alias for readability
const resolveStatus = resolveRunStatus

function fmtNum(n: number): string {
  return n.toLocaleString()
}

export interface LiveRun {
  runId: string
  topic: string
  status: RunStatus
  cost: number
  workflowId?: string | null
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
  collapsed: boolean
  onToggle: () => void
  width: number
  onWidthChange: (w: number) => void
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

export function Sidebar({
  liveRun,
  selectedWorkflowId,
  isLiveRunSelected,
  onSelectLiveRun,
  onSelectHistory,
  onNewReview,
  onResume,
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
    liveRun?.status === "streaming" || liveRun?.status === "connecting"

  async function handleSelectHistory(entry: HistoryEntry) {
    setOpeningId(entry.workflow_id)
    try {
      await onSelectHistory(entry)
    } finally {
      setOpeningId(null)
    }
  }

  async function handleResume(e: React.MouseEvent, entry: HistoryEntry) {
    e.stopPropagation()
    if (!onResume) return
    setResumingId(entry.workflow_id)
    try {
      await onResume(entry)
    } finally {
      setResumingId(null)
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
        {/* Logo row */}
        <div className="flex items-center h-14 border-b border-zinc-800 shrink-0 px-3.5 gap-2">
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
        </div>

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
                <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
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
              <div className="space-y-0.5">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="pl-2.5 pr-2 py-2 rounded-r-md border-l-2 border-zinc-700">
                    <div className="h-2.5 bg-zinc-800 rounded animate-pulse w-3/4 mb-1.5" />
                    <div className="h-2 bg-zinc-800 rounded animate-pulse w-1/2" />
                  </div>
                ))}
              </div>
            )}

            <div className="space-y-0.5">
              {/* Live run floats to the top with pulsing dot and "Now" badge */}
              {liveRun && (
                <SidebarTooltip label={liveRun.topic} collapsed={collapsed} side="right">
                  <button
                    onClick={onSelectLiveRun}
                    className={cn(
                      "w-full transition-colors text-left",
                      collapsed
                        ? "flex justify-center items-center h-9 w-9 mx-auto rounded-lg"
                        : cn(
                            "border-l-2 pl-2.5 pr-2 py-2 rounded-r-md",
                            STATUS_BORDER[liveRun.status],
                          ),
                      isLiveRunSelected
                        ? "bg-zinc-800"
                        : "hover:bg-zinc-800/60",
                    )}
                  >
                    {collapsed ? (
                      <RunDot status={liveRun.status} animate={isRunning} />
                    ) : (
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <RunDot status={liveRun.status} animate={isRunning} />
                          <span
                            className={cn(
                              "text-[10px] font-semibold uppercase tracking-wide shrink-0",
                              STATUS_TEXT[liveRun.status],
                            )}
                          >
                            {STATUS_LABEL[liveRun.status]}
                          </span>
                          <span className="ml-auto text-[10px] text-zinc-500 shrink-0">
                            Now
                          </span>
                        </div>
                        <span className="text-xs text-zinc-300 line-clamp-2 leading-snug">
                          {liveRun.topic}
                        </span>
                        {liveRun.cost > 0 && (
                          <span className="text-[10px] font-mono text-zinc-500 mt-0.5">
                            ${liveRun.cost.toFixed(3)}
                          </span>
                        )}
                      </div>
                    )}
                  </button>
                </SidebarTooltip>
              )}

              {(liveRun?.workflowId
                ? history.filter((e) => e.workflow_id !== liveRun.workflowId)
                : history
              ).map((entry) => {
                const statusKey = resolveStatus(entry.status)
                const isSelected = selectedWorkflowId === entry.workflow_id
                const isOpening = openingId === entry.workflow_id
                const canOpen = Boolean(entry.db_path)
                const borderColor = STATUS_BORDER[statusKey]

                // Build stat chips { value, label, color }
                interface StatChip { value: string; label: string; valColor: string }
                const statChips: StatChip[] = []
                if (entry.papers_found != null && entry.papers_found > 0) {
                  statChips.push({ value: fmtNum(entry.papers_found), label: "found", valColor: "text-blue-400" })
                }
                if (entry.papers_included != null) {
                  statChips.push({ value: fmtNum(entry.papers_included), label: "incl.", valColor: "text-emerald-400" })
                }
                if (entry.artifacts_count != null && entry.artifacts_count > 0) {
                  statChips.push({ value: String(entry.artifacts_count), label: "out", valColor: "text-violet-400" })
                }
                if (entry.total_cost != null && entry.total_cost > 0) {
                  statChips.push({ value: `$${entry.total_cost.toFixed(2)}`, label: "", valColor: "text-amber-400" })
                }

                const isResumable = onResume !== undefined &&
                  ["streaming", "cancelled", "error", "stale"].includes(statusKey)
                const isResuming = resumingId === entry.workflow_id

                return (
                  <SidebarTooltip
                    key={entry.workflow_id}
                    label={entry.topic}
                    collapsed={collapsed}
                    side="right"
                  >
                    <div className="relative group">
                      <button
                        onClick={() => canOpen && void handleSelectHistory(entry)}
                        disabled={!canOpen}
                        className={cn(
                          "w-full transition-colors text-left",
                          collapsed
                            ? "flex justify-center items-center h-9 w-9 mx-auto rounded-lg"
                            : cn(
                                "border-l-2 pl-2.5 pr-2 py-2 rounded-r-md",
                                borderColor,
                              ),
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
                          <div className="flex flex-col gap-0.5 min-w-0">
                            <div className="flex items-center gap-1.5 min-w-0">
                              {isOpening ? (
                                <div className="h-1.5 w-1.5 rounded-full border border-zinc-500 animate-spin shrink-0" />
                              ) : (
                                <RunDot status={statusKey} />
                              )}
                              <span
                                className={cn(
                                  "text-[10px] font-semibold uppercase tracking-wide shrink-0",
                                  STATUS_TEXT[statusKey],
                                )}
                              >
                                {STATUS_LABEL[statusKey]}
                              </span>
                            <span className="ml-auto text-[10px] text-zinc-600 shrink-0 tabular-nums">
                              {formatShortDate(entry.created_at)}
                            </span>
                          </div>
                          <span className="font-mono text-[9px] text-zinc-600 leading-none mb-0.5">
                            {formatWorkflowId(entry.workflow_id)}
                          </span>
                          <span className="text-xs text-zinc-400 line-clamp-2 leading-snug">
                            {entry.topic}
                          </span>
                            {statChips.length > 0 && (
                              <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
                                {statChips.map((chip, idx) => (
                                  <span
                                    key={`${chip.label}-${chip.valColor}-${idx}`}
                                    className="flex items-baseline gap-0.5 tabular-nums leading-none"
                                  >
                                    <span className={`text-[10px] font-semibold ${chip.valColor}`}>
                                      {chip.value}
                                    </span>
                                    {chip.label && (
                                      <span className="text-[9px] text-zinc-600 font-normal">
                                        {chip.label}
                                      </span>
                                    )}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </button>

                      {/* Inline Resume button -- shown on hover for resumable runs */}
                      {isResumable && !collapsed && (
                        <button
                          onClick={(e) => void handleResume(e, entry)}
                          disabled={isResuming}
                          aria-label="Resume run"
                          title="Resume run"
                          className={cn(
                            "absolute top-1.5 right-1.5 flex items-center justify-center",
                            "h-5 w-5 rounded bg-violet-600 hover:bg-violet-500 text-white",
                            "opacity-0 group-hover:opacity-100 transition-opacity duration-150",
                            isResuming && "opacity-100 cursor-wait",
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
                  </SidebarTooltip>
                )
              })}
            </div>

            {!collapsed && history.length === 0 && !loadingHistory && !liveRun && (
              <div className="flex flex-col items-center py-6 gap-2">
                <Clock className="h-6 w-6 text-zinc-700" />
                <p className="text-[11px] text-zinc-600 text-center">
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
    </TooltipProvider>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
