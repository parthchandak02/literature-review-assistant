import { useEffect, useState, useMemo, Suspense, lazy } from "react"
import { AlertTriangle } from "lucide-react"
import { Sidebar, type NavTab } from "@/components/Sidebar"
import { useSSEStream } from "@/hooks/useSSEStream"
import { useCostStats } from "@/hooks/useCostStats"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import { attachHistory, cancelRun, fetchArtifacts, getDefaultReviewConfig, startRun } from "@/lib/api"
import type { HistoryEntry, RunRequest } from "@/lib/api"

const SetupView = lazy(() => import("@/views/SetupView").then((m) => ({ default: m.SetupView })))
const OverviewView = lazy(() => import("@/views/OverviewView").then((m) => ({ default: m.OverviewView })))
const CostView = lazy(() => import("@/views/CostView").then((m) => ({ default: m.CostView })))
const DatabaseView = lazy(() => import("@/views/DatabaseView").then((m) => ({ default: m.DatabaseView })))
const LogView = lazy(() => import("@/views/LogView").then((m) => ({ default: m.LogView })))
const ResultsView = lazy(() => import("@/views/ResultsView").then((m) => ({ default: m.ResultsView })))
const HistoryView = lazy(() => import("@/views/HistoryView").then((m) => ({ default: m.HistoryView })))

const TAB_LABELS: Record<NavTab, string> = {
  setup: "New Review",
  overview: "Overview",
  cost: "Cost & Usage",
  database: "Database Explorer",
  log: "Event Log",
  results: "Results",
  history: "History",
}

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="h-5 w-5 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("history")
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  // --- Live SSE run (never touched when opening historical runs) ---
  const [runId, setRunId] = useState<string | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  const [startedAt, setStartedAt] = useState<Date | null>(null)

  // --- DB Explorer target (independent of the SSE connection) ---
  // Separating these from the live SSE state prevents handleAttach from
  // killing the live stream when browsing historical runs.
  const [dbRunId, setDbRunId] = useState<string | null>(null)
  const [dbIsDone, setDbIsDone] = useState(false)
  const [dbTopic, setDbTopic] = useState<string | null>(null)
  const [dbWorkflowId, setDbWorkflowId] = useState<string | null>(null)

  // Artifacts fetched from run_summary.json for historically-attached runs.
  const [historyOutputs, setHistoryOutputs] = useState<Record<string, string>>({})

  const [defaultYaml, setDefaultYaml] = useState("")

  const { events, status, error, abort, reset } = useSSEStream(runId)
  const costStats = useCostStats(events)
  const { isOnline } = useBackendHealth()

  const isRunning = status === "streaming" || status === "connecting"

  // hasRun controls whether sidebar run-specific tabs are enabled.
  const hasRun = runId !== null || dbRunId !== null

  // Derive outputs from events -- no separate state needed.
  const outputs = useMemo<Record<string, unknown>>(() => {
    if (status !== "done") return {}
    const ev = [...events].reverse().find((e) => e.type === "done")
    return ev?.type === "done" ? ev.outputs : {}
  }, [status, events])

  // dbUnlocked: true once the backend emits db_ready, the run finishes, or we
  // are browsing a historical run (dbIsDone). Derived from existing state.
  const dbUnlocked = useMemo(
    () => dbIsDone || status === "done" || events.some((e) => e.type === "db_ready"),
    [dbIsDone, status, events],
  )

  // Active context for the breadcrumb: live run takes priority over historical.
  const activeTopic = topic ?? dbTopic
  const activeWorkflowId = runId ?? dbWorkflowId

  // Load default YAML config (silently ignored if backend is offline)
  useEffect(() => {
    getDefaultReviewConfig()
      .then((yaml) => setDefaultYaml(yaml))
      .catch(() => {})
  }, [isOnline]) // re-fetch when backend comes back online

  // Fetch run artifacts for historically-attached runs so ResultsView can show files.
  useEffect(() => {
    if (!dbRunId || !dbIsDone) {
      setHistoryOutputs({})
      return
    }
    fetchArtifacts(dbRunId)
      .then((artifacts) => setHistoryOutputs(artifacts))
      .catch(() => setHistoryOutputs({}))
  }, [dbRunId, dbIsDone])

  // Keyboard shortcut: Cmd+B / Ctrl+B to toggle sidebar
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "b") {
        e.preventDefault()
        setSidebarCollapsed((v) => !v)
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  async function handleStart(req: RunRequest) {
    reset()
    setStartedAt(new Date())
    const res = await startRun(req)
    setRunId(res.run_id)
    setDbRunId(res.run_id)
    setDbIsDone(false)
    setDbTopic(null)
    setDbWorkflowId(null)
    setTopic(res.topic)
    setActiveTab("overview")
  }

  async function handleCancel() {
    if (runId) await cancelRun(runId)
    abort()
  }

  function handleNewReview() {
    setRunId(null)
    setTopic(null)
    setStartedAt(null)
    setDbRunId(null)
    setDbIsDone(false)
    setDbTopic(null)
    setDbWorkflowId(null)
    setHistoryOutputs({})
    reset()
    setActiveTab("setup")
  }

  // Attach a historical run for browsing in the Database Explorer.
  // CRITICAL: do NOT touch runId or call reset() -- that would kill the live SSE stream.
  async function handleAttach(entry: HistoryEntry) {
    const res = await attachHistory(entry)
    setDbRunId(res.run_id)
    setDbIsDone(true)
    setDbTopic(entry.topic)
    setDbWorkflowId(entry.workflow_id)
    setActiveTab("database")
  }

  function renderView() {
    switch (activeTab) {
      case "setup":
        return (
          <SetupView
            defaultReviewYaml={defaultYaml}
            onSubmit={handleStart}
            disabled={isRunning}
          />
        )
      case "overview":
        return (
          <OverviewView
            events={events}
            status={status}
            topic={topic ?? ""}
            runId={runId ?? ""}
            costStats={costStats}
            startedAt={startedAt}
            onCancel={handleCancel}
            onTabChange={setActiveTab}
          />
        )
      case "cost":
        return <CostView costStats={costStats} />
      case "database":
        return (
          <DatabaseView
            runId={dbRunId ?? ""}
            isDone={dbIsDone || status === "done"}
            dbAvailable={dbUnlocked}
            isLive={dbUnlocked && !dbIsDone && status !== "done" && status !== "error" && status !== "cancelled"}
          />
        )
      case "log":
        return <LogView events={events} />
      case "results":
        return (
          <ResultsView
            outputs={outputs}
            isDone={status === "done"}
            historyOutputs={historyOutputs}
            exportRunId={status === "done" ? runId : dbIsDone ? dbRunId : null}
          />
        )
      case "history":
        return <HistoryView onAttach={handleAttach} />
      default:
        return null
    }
  }

  const sidebarWidth = sidebarCollapsed ? "ml-[56px]" : "ml-[220px]"

  return (
    <div className="flex h-screen bg-[#09090b] text-zinc-100 overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        hasRun={hasRun}
        isRunning={isRunning}
        runStatus={status}
        totalCost={costStats.total_cost}
        topic={topic}
        onNewReview={handleNewReview}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      {/* Main content area */}
      <main
        className={`flex-1 h-full overflow-y-auto transition-[margin-left] duration-200 ease-in-out ${sidebarWidth}`}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-10 bg-[#09090b]/80 backdrop-blur-sm border-b border-zinc-800 h-14 flex items-center px-6 gap-4">
          {/* Breadcrumb: LitReview / {topic} / {tab} */}
          <div className="flex items-center gap-1.5 text-sm flex-1 min-w-0">
            <span className="text-zinc-600 font-medium shrink-0">LitReview</span>
            {activeTopic && (
              <>
                <span className="text-zinc-700 shrink-0">/</span>
                <span
                  className="text-zinc-500 font-medium truncate max-w-[200px] shrink-0"
                  title={activeTopic}
                >
                  {activeTopic.length > 40 ? activeTopic.slice(0, 40) + "..." : activeTopic}
                </span>
              </>
            )}
            <span className="text-zinc-700 shrink-0">/</span>
            <span className="text-zinc-300 font-medium truncate">{TAB_LABELS[activeTab]}</span>
          </div>

          {/* Workflow ID chip -- shows which run is active */}
          {activeWorkflowId && (
            <span className="font-mono text-[11px] text-zinc-600 hidden sm:block shrink-0">
              {activeWorkflowId.slice(0, 12)}
            </span>
          )}

          {/* Live cost pill */}
          {runId !== null && costStats.total_cost > 0 && (
            <button
              onClick={() => setActiveTab("cost")}
              className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1 hover:bg-emerald-500/15 transition-colors"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="text-xs font-mono font-medium text-emerald-400">
                ${costStats.total_cost.toFixed(4)}
              </span>
            </button>
          )}

          {/* Status badge */}
          {isRunning && (
            <div className="flex items-center gap-1.5 text-xs text-violet-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
              </span>
              Running
            </div>
          )}
          {runId !== null && status === "done" && (
            <span className="text-xs text-emerald-400 font-medium">Complete</span>
          )}
          {status === "error" && (
            <span className="text-xs text-red-400 font-medium" title={error ?? ""}>
              {error?.includes("Backend") ? "Backend offline" : "Error"}
            </span>
          )}
          {status === "cancelled" && (
            <span className="text-xs text-amber-400 font-medium">Cancelled</span>
          )}
        </header>

        {/* Backend offline banner -- shown below the topbar so it's always visible */}
        {!isOnline && (
          <div className="flex items-center gap-2.5 bg-amber-500/10 border-b border-amber-500/20 px-6 py-2.5 text-xs text-amber-400">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span className="font-medium">Backend offline.</span>
            <span className="text-amber-500/70">
              Start it with:{" "}
              <code className="font-mono bg-amber-500/10 px-1 py-0.5 rounded">
                uv run uvicorn src.web.app:app --reload --port 8000
              </code>
            </span>
          </div>
        )}

        {/* View content */}
        <div className="p-6">
          <Suspense fallback={<ViewLoader />}>
            {renderView()}
          </Suspense>
        </div>
      </main>
    </div>
  )
}
