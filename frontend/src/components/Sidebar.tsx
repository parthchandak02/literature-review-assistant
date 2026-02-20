import { useCallback, useEffect, useState } from "react"
import {
  BookMarked,
  ChevronLeft,
  ChevronRight,
  Clock,
  Plus,
  RefreshCw,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { fetchHistory } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RunStatus = "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled"

const STATUS_LABEL: Record<RunStatus, string> = {
  idle: "Ready",
  connecting: "Connecting",
  streaming: "Running",
  done: "Completed",
  error: "Failed",
  cancelled: "Cancelled",
}

const STATUS_DOT: Record<RunStatus, string> = {
  idle: "bg-zinc-600",
  connecting: "bg-violet-400",
  streaming: "bg-violet-500",
  done: "bg-emerald-500",
  error: "bg-red-500",
  cancelled: "bg-amber-500",
}

const STATUS_TEXT: Record<RunStatus, string> = {
  idle: "text-zinc-500",
  connecting: "text-violet-400",
  streaming: "text-violet-400",
  done: "text-emerald-400",
  error: "text-red-400",
  cancelled: "text-amber-400",
}

const STATUS_BORDER: Record<RunStatus, string> = {
  idle: "border-zinc-700",
  connecting: "border-violet-500",
  streaming: "border-violet-500",
  done: "border-emerald-500",
  error: "border-red-500",
  cancelled: "border-amber-500",
}

function resolveStatus(raw: string): RunStatus {
  const s = raw.toLowerCase()
  if (s === "completed" || s === "done") return "done"
  if (s === "running" || s === "streaming") return "streaming"
  if (s === "connecting") return "connecting"
  if (s === "error" || s === "failed") return "error"
  if (s === "cancelled" || s === "canceled") return "cancelled"
  return "idle"
}

function fmtNum(n: number): string {
  return n.toLocaleString()
}

export interface LiveRun {
  runId: string
  topic: string
  status: RunStatus
  cost: number
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
  collapsed: boolean
  onToggle: () => void
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
  collapsed,
  onToggle,
}: SidebarProps) {
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)

  const loadHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const data = await fetchHistory()
      setHistory(data)
    } catch {
      // silently ignore -- history is non-critical
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // Fetch history on mount, poll every 15s (picks up in-progress CLI runs),
  // and whenever the live run finishes.
  useEffect(() => {
    void loadHistory()
    const id = setInterval(() => void loadHistory(), 15_000)
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

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          "fixed left-0 top-0 h-full bg-zinc-900 border-r border-zinc-800 flex flex-col z-20 select-none",
          "transition-[width] duration-200 ease-in-out overflow-hidden",
          collapsed ? "w-[56px]" : "w-[240px]",
        )}
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

        {/* Run list */}
        <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2.5 pb-2 space-y-4">
          {/* Current / live run */}
          {liveRun && (
            <section>
              {!collapsed && (
                <div className="px-1 mb-1.5">
                  <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
                    Current
                  </span>
                </div>
              )}
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
            </section>
          )}

          {/* History */}
          <section>
            {!collapsed && (
              <div className="flex items-center justify-between px-1 mb-1.5">
                <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider">
                  History
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

            <div className="space-y-0.5">
              {history.map((entry) => {
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

                return (
                  <SidebarTooltip
                    key={entry.workflow_id}
                    label={entry.topic}
                    collapsed={collapsed}
                    side="right"
                  >
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
                          <span className="text-xs text-zinc-400 line-clamp-2 leading-snug">
                            {entry.topic}
                          </span>
                          {statChips.length > 0 && (
                            <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1">
                              {statChips.map((chip) => (
                                <span
                                  key={chip.label || chip.valColor}
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
                  </SidebarTooltip>
                )
              })}
            </div>

            {!collapsed && history.length === 0 && !loadingHistory && (
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

function formatShortDate(raw: string): string {
  if (!raw) return ""
  try {
    const d = new Date(raw.includes("T") ? raw : raw.replace(" ", "T") + "Z")
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7)
      return d.toLocaleDateString(undefined, { weekday: "short" })
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
  } catch {
    return raw.slice(0, 10)
  }
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
