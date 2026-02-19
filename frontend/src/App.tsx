import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { RunForm } from "@/components/RunForm"
import { PhaseProgress } from "@/components/PhaseProgress"
import { LogStream } from "@/components/LogStream"
import { ResultsPanel } from "@/components/ResultsPanel"
import { useSSEStream } from "@/hooks/useSSEStream"
import { cancelRun, getDefaultReviewConfig, startRun } from "@/lib/api"
import type { RunRequest } from "@/lib/api"
import { BookOpen, XCircle } from "lucide-react"

type AppView = "setup" | "running" | "done"

function statusBadge(status: string) {
  if (status === "streaming") return <Badge variant="outline" className="border-primary/50 text-primary animate-pulse">Running</Badge>
  if (status === "connecting") return <Badge variant="outline" className="text-muted-foreground">Connecting...</Badge>
  if (status === "done") return <Badge className="bg-green-600 text-white">Complete</Badge>
  if (status === "error") return <Badge variant="destructive">Error</Badge>
  if (status === "cancelled") return <Badge variant="outline" className="text-muted-foreground">Cancelled</Badge>
  return null
}

export default function App() {
  const [view, setView] = useState<AppView>("setup")
  const [runId, setRunId] = useState<string | null>(null)
  const [topic, setTopic] = useState<string>("")
  const [defaultYaml, setDefaultYaml] = useState("")
  const [outputs, setOutputs] = useState<Record<string, unknown>>({})

  const { events, status, error, abort, reset } = useSSEStream(runId)

  // Load default review config on mount
  useEffect(() => {
    getDefaultReviewConfig()
      .then((yaml) => setDefaultYaml(yaml))
      .catch(() => {})
  }, [])

  // When stream finishes, collect outputs from done event
  useEffect(() => {
    if (status === "done") {
      const doneEvent = [...events].reverse().find((e) => e.type === "done")
      if (doneEvent && doneEvent.type === "done") {
        setOutputs(doneEvent.outputs)
      }
      setView("done")
    }
  }, [status, events])

  async function handleStart(req: RunRequest) {
    reset()
    setOutputs({})
    const res = await startRun(req)
    setRunId(res.run_id)
    setTopic(res.topic)
    setView("running")
  }

  async function handleCancel() {
    if (runId) await cancelRun(runId)
    abort()
    setView("done")
  }

  function handleNewReview() {
    setRunId(null)
    setTopic("")
    setOutputs({})
    reset()
    setView("setup")
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <BookOpen className="h-5 w-5 text-primary" />
            <span className="font-semibold tracking-tight text-sm">Research Review</span>
          </div>
          <div className="flex items-center gap-3">
            {statusBadge(status)}
            {view === "running" && (
              <Button
                size="sm"
                variant="destructive"
                onClick={handleCancel}
                className="gap-1.5"
              >
                <XCircle className="h-3.5 w-3.5" />
                Cancel
              </Button>
            )}
            {(view === "done" || view === "running") && (
              <Button size="sm" variant="outline" onClick={handleNewReview}>
                New Review
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Main layout */}
      <main className="max-w-5xl mx-auto px-4 py-8">
        {view === "setup" && (
          <div className="max-w-2xl mx-auto">
            <div className="mb-8 text-center">
              <h1 className="text-2xl font-bold tracking-tight mb-2">Systematic Review Automation</h1>
              <p className="text-muted-foreground text-sm max-w-md mx-auto">
                Configure your review topic and API keys, then start a fully automated systematic
                literature review pipeline.
              </p>
            </div>
            <RunForm
              defaultReviewYaml={defaultYaml}
              onSubmit={handleStart}
              disabled={view !== "setup"}
            />
          </div>
        )}

        {(view === "running" || view === "done") && (
          <div className="flex flex-col gap-6">
            {/* Topic header */}
            <div>
              <h1 className="text-lg font-semibold tracking-tight leading-snug line-clamp-2">
                {topic}
              </h1>
              {runId && (
                <p className="text-xs text-muted-foreground mt-0.5">Run ID: {runId}</p>
              )}
              {error && (
                <p className="text-sm text-destructive mt-2">{error}</p>
              )}
            </div>

            <Separator />

            {/* Two-column layout on wide screens */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left: phase progress */}
              <div>
                <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">
                  Phases
                </h2>
                <PhaseProgress events={events} status={status} />
              </div>

              {/* Right: log stream + results */}
              <div className="flex flex-col gap-6">
                <div>
                  <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">
                    Event Log
                  </h2>
                  <LogStream events={events} />
                </div>

                {view === "done" && Object.keys(outputs).length > 0 && (
                  <div>
                    <h2 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wide">
                      Results
                    </h2>
                    <ResultsPanel outputs={outputs} />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
