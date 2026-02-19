import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CheckCircle, Circle, Loader } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ReviewEvent } from "@/lib/api"

const PHASE_ORDER = [
  "search",
  "screening",
  "extraction",
  "quality",
  "synthesis",
  "writing",
]

const PHASE_LABELS: Record<string, string> = {
  search: "Search",
  screening: "Screening",
  extraction: "Extraction",
  quality: "Quality Assessment",
  synthesis: "Synthesis",
  writing: "Writing",
}

type PhaseStatus = "pending" | "running" | "done"

interface PhaseState {
  status: PhaseStatus
  progress?: { current: number; total: number }
  summary?: Record<string, unknown>
}

function buildPhaseStates(events: ReviewEvent[]): Record<string, PhaseState> {
  const states: Record<string, PhaseState> = {}
  for (const ev of events) {
    if (ev.type === "phase_start") {
      states[ev.phase] = { status: "running" }
    } else if (ev.type === "phase_done") {
      states[ev.phase] = {
        status: "done",
        summary: ev.summary,
        progress: ev.total != null && ev.completed != null
          ? { current: ev.completed, total: ev.total }
          : undefined,
      }
    } else if (ev.type === "progress") {
      if (states[ev.phase]) {
        states[ev.phase].progress = { current: ev.current, total: ev.total }
      }
    }
  }
  return states
}

interface PhaseProgressProps {
  events: ReviewEvent[]
  status: string
}

export function PhaseProgress({ events, status }: PhaseProgressProps) {
  const phaseStates = buildPhaseStates(events)

  const screeningDecisions = events.filter((e) => e.type === "screening_decision")
  const included = screeningDecisions.filter(
    (e) => e.type === "screening_decision" && e.decision === "include",
  ).length

  const connectorResults = events.filter((e) => e.type === "connector_result" && e.status === "success")
  const totalFound = connectorResults.reduce(
    (acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0),
    0,
  )

  return (
    <div className="flex flex-col gap-3">
      {/* Summary strip */}
      {(totalFound > 0 || included > 0) && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-3 pb-3 flex gap-6 flex-wrap text-sm">
            {totalFound > 0 && (
              <div>
                <span className="font-semibold text-white tabular-nums">{totalFound.toLocaleString()}</span>
                <span className="text-zinc-500 ml-1">papers found</span>
              </div>
            )}
            {included > 0 && (
              <div>
                <span className="font-semibold text-white tabular-nums">{included}</span>
                <span className="text-zinc-500 ml-1">included</span>
              </div>
            )}
            {status === "done" && (
              <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30 border">Complete</Badge>
            )}
            {status === "error" && (
              <Badge variant="destructive">Error</Badge>
            )}
          </CardContent>
        </Card>
      )}

      {/* Phase cards */}
      {PHASE_ORDER.map((phase) => {
        const state = phaseStates[phase] ?? { status: "pending" as PhaseStatus }
        const label = PHASE_LABELS[phase] ?? phase
        const progressVal =
          state.progress != null && state.progress.total > 0
            ? Math.round((state.progress.current / state.progress.total) * 100)
            : state.status === "done"
            ? 100
            : state.status === "running"
            ? undefined
            : 0

        return (
          <Card
            key={phase}
            className={cn(
              "border transition-colors",
              state.status === "running"
                ? "border-violet-500/40 bg-violet-500/5"
                : state.status === "done"
                ? "border-emerald-500/30 bg-zinc-900"
                : "border-zinc-800 bg-zinc-900 opacity-50",
            )}
          >
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-sm font-medium flex items-center gap-2 text-zinc-200">
                {state.status === "done" ? (
                  <CheckCircle className="h-4 w-4 text-emerald-500 shrink-0" />
                ) : state.status === "running" ? (
                  <Loader className="h-4 w-4 text-violet-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="h-4 w-4 text-zinc-700 shrink-0" />
                )}
                {label}
                {state.status === "running" && (
                  <Badge className="ml-auto text-xs border border-violet-500/40 text-violet-400 bg-transparent">
                    Running
                  </Badge>
                )}
                {state.status === "done" && (
                  <Badge className="ml-auto text-xs border border-emerald-500/30 text-emerald-400 bg-transparent">
                    Done
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            {state.status !== "pending" && (
              <CardContent className="pb-3 px-4 flex flex-col gap-2">
                <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-300",
                      state.status === "done" ? "bg-emerald-500" : "bg-violet-500",
                    )}
                    style={{
                      width: progressVal !== undefined ? `${progressVal}%` : "40%",
                    }}
                  />
                </div>
                {state.status === "done" && state.summary && Object.keys(state.summary).length > 0 && (
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-zinc-500">
                    {Object.entries(state.summary).slice(0, 6).map(([k, v]) => (
                      <span key={k}>
                        <span className="font-medium text-zinc-300">{String(v)}</span>{" "}
                        {k.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
                {state.status === "running" && state.progress && (
                  <p className="text-xs text-zinc-500 tabular-nums">
                    {state.progress.current} / {state.progress.total}
                  </p>
                )}
              </CardContent>
            )}
          </Card>
        )
      })}
    </div>
  )
}
