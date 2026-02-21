import { useEffect, useMemo, useState, Suspense, lazy } from "react"
import { AlertTriangle } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import type { LiveRun } from "@/components/Sidebar"
import { useSSEStream } from "@/hooks/useSSEStream"
import { useCostStats } from "@/hooks/useCostStats"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import {
  attachHistory,
  cancelRun,
  fetchArtifacts,
  getDefaultReviewConfig,
  saveLiveRun,
  loadLiveRun,
  clearLiveRun,
  startRun,
} from "@/lib/api"
import type { HistoryEntry, RunRequest, RunResponse } from "@/lib/api"
import { RunView } from "@/views/RunView"
import type { RunTab, SelectedRun } from "@/views/RunView"
import { HistoryView } from "@/views/HistoryView"

const SetupView = lazy(() => import("@/views/SetupView").then((m) => ({ default: m.SetupView })))

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="h-5 w-5 rounded-full border-2 border-violet-500 border-t-transparent animate-spin" />
    </div>
  )
}


export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [showSetup, setShowSetup] = useState(false)
  const [defaultYaml, setDefaultYaml] = useState("")

  // --- Live SSE run ---
  // runId drives the SSE connection. Only set when the user starts a run in
  // this browser session (or restores from localStorage on page refresh).
  const [liveRunId, setLiveRunId] = useState<string | null>(null)
  const [liveTopic, setLiveTopic] = useState<string | null>(null)
  const [liveStartedAt, setLiveStartedAt] = useState<Date | null>(null)

  // --- Selected run (what is displayed in the main area) ---
  // Distinct from liveRunId: can be a historical run while a live one streams.
  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)
  const [activeRunTab, setActiveRunTab] = useState<RunTab>("activity")

  // Artifacts for historical ResultsView
  const [historyOutputs, setHistoryOutputs] = useState<Record<string, string>>({})

  const { events, status, error, abort, reset } = useSSEStream(liveRunId)
  const costStats = useCostStats(events)
  const { isOnline } = useBackendHealth()

  const isRunning = status === "streaming" || status === "connecting"

  // Outputs from the live "done" event (in-memory, cleared on new run).
  const liveOutputs = useMemo<Record<string, unknown>>(() => {
    if (status !== "done") return {}
    const ev = [...events].reverse().find((e) => e.type === "done")
    return ev?.type === "done" ? ev.outputs : {}
  }, [status, events])

  // True once db_ready is emitted or the run is done / historical.
  const dbUnlocked = useMemo(
    () =>
      selectedRun?.isDone ||
      status === "done" ||
      events.some((e) => e.type === "db_ready"),
    [selectedRun?.isDone, status, events],
  )

  // True when the currently viewed run is the live SSE run (not a historical one).
  const isViewingLiveRun = selectedRun !== null && selectedRun.runId === liveRunId

  // Events to pass to RunView: only provide live events when viewing the live run.
  const viewEvents = isViewingLiveRun ? events : []

  // Sidebar live run descriptor
  const liveRunForSidebar: LiveRun | null = liveRunId
    ? {
        runId: liveRunId,
        topic: liveTopic ?? "",
        status,
        cost: costStats.total_cost,
      }
    : null

  // --- localStorage restore: reconnect to a live run after page refresh ---
  useEffect(() => {
    const stored = loadLiveRun()
    if (!stored) return
    setLiveRunId(stored.runId)
    setLiveTopic(stored.topic)
    setLiveStartedAt(new Date(stored.startedAt))
    setSelectedRun({
      runId: stored.runId,
      workflowId: null,
      topic: stored.topic,
      dbPath: null,
      isDone: false,
      startedAt: new Date(stored.startedAt),
      createdAt: stored.startedAt,
    })
  }, [])

  // Clear localStorage when the live run reaches a terminal state.
  useEffect(() => {
    if (status === "done" || status === "error" || status === "cancelled") {
      clearLiveRun()
    }
  }, [status])

  // Update selectedRun workflowId once the live run outputs are available.
  useEffect(() => {
    if (!liveOutputs || !liveRunId) return
    const wfId = liveOutputs.workflow_id as string | undefined
    if (wfId && selectedRun?.runId === liveRunId && !selectedRun?.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: wfId, isDone: true } : r))
    }
  }, [liveOutputs, liveRunId, selectedRun])

  // Load default YAML config (silently ignored if backend is offline)
  useEffect(() => {
    getDefaultReviewConfig()
      .then((yaml) => setDefaultYaml(yaml))
      .catch(() => {})
  }, [isOnline])

  // Fetch artifacts for ResultsView when viewing a completed historical run.
  useEffect(() => {
    if (!selectedRun?.isDone || isViewingLiveRun) {
      setHistoryOutputs({})
      return
    }
    fetchArtifacts(selectedRun.runId)
      .then((artifacts) => setHistoryOutputs(artifacts))
      .catch(() => setHistoryOutputs({}))
  }, [selectedRun?.runId, selectedRun?.isDone, isViewingLiveRun])

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

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleStart(req: RunRequest) {
    reset()
    const now = new Date()
    const res = await startRun(req)
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    saveLiveRun({ runId: res.run_id, topic: res.topic, startedAt: now.toISOString() })
    const run: SelectedRun = {
      runId: res.run_id,
      workflowId: null,
      topic: res.topic,
      dbPath: null,
      isDone: false,
      startedAt: now,
      createdAt: now.toISOString(),
    }
    setSelectedRun(run)
    setActiveRunTab("activity")
    setShowSetup(false)
  }

  async function handleCancel() {
    if (liveRunId) await cancelRun(liveRunId)
    abort()
  }

  function handleNewReview() {
    setShowSetup(true)
    setSelectedRun(null)
    setHistoryOutputs({})
  }

  function handleSelectLiveRun() {
    if (!liveRunId || !liveTopic) return
    setSelectedRun({
      runId: liveRunId,
      workflowId: null,
      topic: liveTopic,
      dbPath: null,
      isDone: status === "done" || status === "error" || status === "cancelled",
      startedAt: liveStartedAt,
      createdAt: liveStartedAt?.toISOString() ?? null,
    })
    setShowSetup(false)
  }

  async function handleSelectHistory(entry: HistoryEntry) {
    const res = await attachHistory(entry)
    setSelectedRun({
      runId: res.run_id,
      workflowId: entry.workflow_id,
      topic: entry.topic,
      dbPath: entry.db_path,
      isDone: true,
      startedAt: null,
      createdAt: entry.created_at,
      papersFound: entry.papers_found ?? null,
      papersIncluded: entry.papers_included ?? null,
      historicalCost: entry.total_cost ?? null,
    })
    setShowSetup(false)
  }

  function handleResumeRun(res: RunResponse) {
    const now = new Date()
    reset()
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    saveLiveRun({ runId: res.run_id, topic: res.topic, startedAt: now.toISOString() })
    const run: SelectedRun = {
      runId: res.run_id,
      workflowId: null,
      topic: res.topic,
      dbPath: null,
      isDone: false,
      startedAt: now,
      createdAt: now.toISOString(),
    }
    setSelectedRun(run)
    setActiveRunTab("activity")
    setShowSetup(false)
  }

  // ---------------------------------------------------------------------------
  // Layout
  // ---------------------------------------------------------------------------

  const sidebarWidth = sidebarCollapsed ? "ml-[56px]" : "ml-[240px]"

  function renderMain() {
    if (showSetup || selectedRun === null) {
      if (showSetup) {
        return (
          <Suspense fallback={<ViewLoader />}>
            <SetupView
              defaultReviewYaml={defaultYaml}
              onSubmit={handleStart}
              disabled={isRunning}
            />
          </Suspense>
        )
      }
      return (
        <div className="flex-1 overflow-y-auto p-6">
          <HistoryView
            onAttach={handleSelectHistory}
            onResume={handleResumeRun}
          />
        </div>
      )
    }

    return (
      <RunView
        run={selectedRun}
        events={viewEvents}
        status={isViewingLiveRun ? status : "done"}
        costStats={isViewingLiveRun ? costStats : { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] }}
        activeTab={activeRunTab}
        onTabChange={setActiveRunTab}
        onCancel={handleCancel}
        historyOutputs={historyOutputs}
        liveOutputs={isViewingLiveRun ? liveOutputs : {}}
        dbUnlocked={Boolean(dbUnlocked)}
        isLive={isViewingLiveRun && isRunning && Boolean(dbUnlocked)}
      />
    )
  }

  // Breadcrumb
  const breadcrumbTopic = selectedRun?.topic ?? null
  const breadcrumbTab = showSetup
    ? "New Review"
    : selectedRun
      ? (
          activeRunTab.charAt(0).toUpperCase() + activeRunTab.slice(1)
        )
      : "Home"

  return (
    <div className="flex h-screen bg-[#09090b] text-zinc-100 overflow-hidden">
      <Sidebar
        liveRun={liveRunForSidebar}
        selectedWorkflowId={selectedRun?.workflowId ?? null}
        isLiveRunSelected={isViewingLiveRun}
        onSelectLiveRun={handleSelectLiveRun}
        onSelectHistory={(entry) => void handleSelectHistory(entry)}
        onNewReview={handleNewReview}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
      />

      <main
        className={`flex-1 h-full overflow-hidden flex flex-col transition-[margin-left] duration-200 ease-in-out ${sidebarWidth}`}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-10 bg-[#09090b]/80 backdrop-blur-sm border-b border-zinc-800 h-14 flex items-center px-6 gap-4 shrink-0">
          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 text-sm flex-1 min-w-0">
            <span className="text-zinc-600 font-medium shrink-0">LitReview</span>
            {breadcrumbTopic && (
              <>
                <span className="text-zinc-700 shrink-0">/</span>
                <span
                  className="text-zinc-500 font-medium truncate max-w-[220px] shrink-0"
                  title={breadcrumbTopic}
                >
                  {breadcrumbTopic.length > 45
                    ? breadcrumbTopic.slice(0, 45) + "..."
                    : breadcrumbTopic}
                </span>
              </>
            )}
            <span className="text-zinc-700 shrink-0">/</span>
            <span className="text-zinc-300 font-medium truncate">{breadcrumbTab}</span>
          </div>

          {/* Workflow ID chip */}
          {selectedRun?.workflowId && (
            <span className="font-mono text-[11px] text-zinc-600 hidden sm:block shrink-0">
              {selectedRun.workflowId.slice(0, 12)}
            </span>
          )}

          {/* Live cost pill */}
          {isViewingLiveRun && costStats.total_cost > 0 && (
            <button
              onClick={() => setActiveRunTab("cost")}
              className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1 hover:bg-emerald-500/15 transition-colors"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="text-xs font-mono font-medium text-emerald-400">
                ${costStats.total_cost.toFixed(4)}
              </span>
            </button>
          )}

          {/* Status badge */}
          {isViewingLiveRun && isRunning && (
            <div className="flex items-center gap-1.5 text-xs text-violet-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
              </span>
              Running
            </div>
          )}
          {isViewingLiveRun && status === "done" && (
            <span className="text-xs text-emerald-400 font-medium">Complete</span>
          )}
          {isViewingLiveRun && status === "error" && (
            <span className="text-xs text-red-400 font-medium" title={error ?? ""}>
              {error?.includes("Backend") ? "Backend offline" : "Error"}
            </span>
          )}
          {isViewingLiveRun && status === "cancelled" && (
            <span className="text-xs text-amber-400 font-medium">Cancelled</span>
          )}
        </header>

        {/* Backend offline banner */}
        {!isOnline && (
          <div className="flex items-center gap-2.5 bg-amber-500/10 border-b border-amber-500/20 px-6 py-2.5 text-xs text-amber-400 shrink-0">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span className="font-medium">Backend offline.</span>
            <span className="text-amber-500/70">
              Start it with:{" "}
              <code className="font-mono bg-amber-500/10 px-1 py-0.5 rounded">
                overmind start -f Procfile.dev
              </code>
            </span>
          </div>
        )}

        {/* Main content */}
        <div
          className={
            selectedRun && !showSetup
              ? "flex-1 overflow-hidden"
              : "flex-1 overflow-y-auto p-6"
          }
        >
          {renderMain()}
        </div>
      </main>
    </div>
  )
}
