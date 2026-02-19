import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { CheckCircle, Circle, Loader } from "lucide-react"
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

  // Count total papers screened for a summary stat
  const screeningDecisions = events.filter((e) => e.type === "screening_decision")
  const included = screeningDecisions.filter(
    (e) => e.type === "screening_decision" && e.decision === "include"
  ).length

  // Connector results for search
  const connectorResults = events.filter((e) => e.type === "connector_result" && e.status === "success")
  const totalFound = connectorResults.reduce(
    (acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0),
    0
  )

  return (
    <div className="flex flex-col gap-3">
      {/* Summary stats strip */}
      {(totalFound > 0 || included > 0) && (
        <Card className="bg-muted/40">
          <CardContent className="pt-4 pb-3 flex gap-6 flex-wrap text-sm">
            {totalFound > 0 && (
              <div>
                <span className="font-semibold text-foreground">{totalFound.toLocaleString()}</span>
                <span className="text-muted-foreground ml-1">papers found</span>
              </div>
            )}
            {included > 0 && (
              <div>
                <span className="font-semibold text-foreground">{included}</span>
                <span className="text-muted-foreground ml-1">included</span>
              </div>
            )}
            {status === "done" && (
              <div>
                <Badge variant="default" className="bg-green-600 text-white">Complete</Badge>
              </div>
            )}
            {status === "error" && (
              <div>
                <Badge variant="destructive">Error</Badge>
              </div>
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
            className={
              state.status === "running"
                ? "border-primary/50 bg-primary/5"
                : state.status === "done"
                ? "border-green-500/30 bg-green-500/5"
                : "opacity-50"
            }
          >
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                {state.status === "done" ? (
                  <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />
                ) : state.status === "running" ? (
                  <Loader className="h-4 w-4 text-primary animate-spin shrink-0" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground shrink-0" />
                )}
                {label}
                {state.status === "running" && (
                  <Badge variant="outline" className="ml-auto text-xs">Running</Badge>
                )}
                {state.status === "done" && (
                  <Badge variant="outline" className="ml-auto text-xs border-green-500/40 text-green-600">Done</Badge>
                )}
              </CardTitle>
            </CardHeader>
            {state.status !== "pending" && (
              <CardContent className="pb-3 px-4 flex flex-col gap-2">
                {progressVal !== undefined ? (
                  <Progress value={progressVal} className="h-1.5" />
                ) : (
                  <Progress value={undefined} className="h-1.5" />
                )}
                {state.status === "done" && state.summary && Object.keys(state.summary).length > 0 && (
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                    {Object.entries(state.summary).slice(0, 6).map(([k, v]) => (
                      <span key={k}>
                        <span className="font-medium text-foreground">{String(v)}</span>{" "}
                        {k.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
                {state.status === "running" && state.progress && (
                  <p className="text-xs text-muted-foreground">
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
