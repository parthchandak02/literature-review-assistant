import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { CheckCircle, Circle, Clock, DollarSign, FileSearch, Layers, Loader, XCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ReviewEvent } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import type { NavTab } from "@/components/Sidebar"

const PHASE_ORDER = ["search", "screening", "extraction", "quality", "synthesis", "writing", "finalize"]
const PHASE_LABELS: Record<string, string> = {
  search: "Search",
  screening: "Screening",
  extraction: "Extraction",
  quality: "Quality Assessment",
  synthesis: "Synthesis",
  writing: "Writing",
  finalize: "Finalize",
}

type PhaseStatus = "pending" | "running" | "done"

interface PhaseState {
  status: PhaseStatus
  progress?: { current: number; total: number }
}

function buildPhaseStates(events: ReviewEvent[]): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = { status: "running" }
    } else if (ev.type === "phase_done") {
      states[ev.phase] = {
        status: "done",
        progress: ev.total != null && ev.completed != null
          ? { current: ev.completed, total: ev.total }
          : undefined,
      }
    } else if (ev.type === "progress" && states[ev.phase]) {
      states[ev.phase].progress = { current: ev.current, total: ev.total }
    }
  }
  return states
}

const TERMINAL_STATUSES = new Set(["done", "error", "cancelled"])

/**
 * Live elapsed timer. Stops ticking when the run reaches a terminal status
 * so the displayed value freezes at the actual run duration.
 * The formatted string is computed only inside the interval callback to avoid
 * calling Date.now() during render (ESLint: no-date-now-during-render).
 */
function useElapsed(startedAt: Date | null, status: string): string {
  const [elapsed, setElapsed] = useState("--")
  const stopped = TERMINAL_STATUSES.has(status)
  useEffect(() => {
    if (!startedAt || stopped) return
    const compute = () => {
      const secs = Math.floor((Date.now() - startedAt.getTime()) / 1000)
      setElapsed(`${Math.floor(secs / 60)}m ${secs % 60}s`)
    }
    const id = setInterval(compute, 1000)
    return () => clearInterval(id)
  }, [startedAt, stopped])
  return elapsed
}

interface StatCardProps {
  icon: React.ElementType
  label: string
  value: string | number
  sub?: string
  accent?: string
  onClick?: () => void
}

function StatCard({ icon: Icon, label, value, sub, accent, onClick }: StatCardProps) {
  return (
    <div
      className={cn(
        "bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex flex-col gap-3",
        onClick && "cursor-pointer hover:border-zinc-700 transition-colors",
      )}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">{label}</span>
        <Icon className={cn("h-4 w-4", accent ?? "text-zinc-600")} />
      </div>
      <div className="text-2xl font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="text-xs text-zinc-500">{sub}</div>}
    </div>
  )
}

interface OverviewViewProps {
  events: ReviewEvent[]
  status: string
  topic: string
  runId: string
  costStats: CostStats
  startedAt: Date | null
  isHistorical?: boolean
  onCancel: () => void
  onTabChange: (tab: NavTab) => void
}

export function OverviewView({
  events,
  status,
  topic,
  runId,
  costStats,
  startedAt,
  isHistorical = false,
  onCancel,
  onTabChange,
}: OverviewViewProps) {
  if (isHistorical) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
        <p className="text-zinc-500 text-sm">
          Overview shows live run progress only.
          This is a completed historical review.
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => onTabChange("database")}>
            Database Explorer
          </Button>
          <Button variant="outline" size="sm" onClick={() => onTabChange("results")}>
            Results
          </Button>
          <Button variant="outline" size="sm" onClick={() => onTabChange("cost")}>
            Cost and Usage
          </Button>
        </div>
      </div>
    )
  }
  const phaseStates = buildPhaseStates(events)
  const elapsed = useElapsed(startedAt, status)
  const isRunning = status === "streaming" || status === "connecting"

  const totalFound = events
    .filter((e) => e.type === "connector_result" && e.status === "success")
    .reduce((acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0), 0)

  const included = events.filter(
    (e) => e.type === "screening_decision" && e.decision === "include",
  ).length

  const phaseDoneCount = PHASE_ORDER.filter((p) => phaseStates[p]?.status === "done").length
  const totalPhases = PHASE_ORDER.length

  return (
    <div className="flex flex-col gap-6">
      {/* Topic + controls */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white leading-snug line-clamp-2 max-w-2xl">
            {topic}
          </h2>
          <p className="text-xs text-zinc-500 mt-1 font-mono">run:{runId}</p>
        </div>
        {isRunning && (
          <Button
            size="sm"
            variant="outline"
            onClick={onCancel}
            className="shrink-0 border-zinc-700 text-zinc-300 hover:text-red-400 hover:border-red-500/40 gap-1.5"
          >
            <XCircle className="h-3.5 w-3.5" />
            Cancel
          </Button>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={FileSearch}
          label="Papers Found"
          value={totalFound.toLocaleString()}
          sub="across all databases"
          accent="text-blue-400"
        />
        <StatCard
          icon={CheckCircle}
          label="Included"
          value={included}
          sub="passed screening"
          accent="text-emerald-400"
        />
        <StatCard
          icon={DollarSign}
          label="Cost So Far"
          value={`$${costStats.total_cost.toFixed(4)}`}
          sub={`${costStats.total_calls} LLM calls`}
          accent="text-violet-400"
          onClick={() => onTabChange("cost")}
        />
        <StatCard
          icon={Clock}
          label="Elapsed"
          value={elapsed}
          sub={`${phaseDoneCount}/${totalPhases} phases done`}
          accent="text-zinc-400"
        />
      </div>

      {/* Phase timeline */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3 flex items-center gap-2">
          <Layers className="h-3.5 w-3.5" />
          Phase Timeline
        </h3>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          {PHASE_ORDER.map((phase, i) => {
            const state = phaseStates[phase] ?? { status: "pending" as PhaseStatus }
            const label = PHASE_LABELS[phase] ?? phase
            const isLast = i === PHASE_ORDER.length - 1
            const progressPct =
              state.progress != null && state.progress.total > 0
                ? Math.round((state.progress.current / state.progress.total) * 100)
                : state.status === "done"
                ? 100
                : 0

            return (
              <div
                key={phase}
                className={cn(
                  "flex items-center gap-4 px-4 py-3",
                  !isLast && "border-b border-zinc-800",
                )}
              >
                {/* Status icon */}
                <div className="shrink-0">
                  {state.status === "done" ? (
                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                  ) : state.status === "running" ? (
                    <Loader className="h-4 w-4 text-violet-400 animate-spin" />
                  ) : (
                    <Circle className="h-4 w-4 text-zinc-700" />
                  )}
                </div>

                {/* Label */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={cn(
                        "text-sm font-medium",
                        state.status === "done"
                          ? "text-zinc-200"
                          : state.status === "running"
                          ? "text-white"
                          : "text-zinc-600",
                      )}
                    >
                      {label}
                    </span>
                    {state.status !== "pending" && (
                      <span className="text-xs tabular-nums text-zinc-500 shrink-0">
                        {progressPct}%
                      </span>
                    )}
                  </div>
                  {/* Progress bar */}
                  {state.status !== "pending" && (
                    <div className="mt-1.5 h-1 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-300",
                          state.status === "done" ? "bg-emerald-500" : "bg-violet-500",
                        )}
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Running sub-info */}
                {state.status === "running" && state.progress && (
                  <div className="shrink-0 text-xs text-zinc-500 tabular-nums">
                    {state.progress.current}/{state.progress.total}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
