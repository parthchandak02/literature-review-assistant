import { useEffect, useMemo, useRef, useState, Suspense, lazy, Component } from "react"
import type { ReactNode, ErrorInfo } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { Toaster, toast } from "sonner"
import { AlertTriangle, BarChart3, Menu } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import type { LiveRun } from "@/components/Sidebar"
import { GlobalCostOpsDialog } from "@/components/GlobalCostOpsDialog"
import { computePhaseProgress } from "@/lib/phaseProgress"
import { computeFunnelStages } from "@/lib/funnelStages"
import { isSameRunSelection } from "@/lib/runSelection"
import { useSSEStream } from "@/hooks/useSSEStream"
import { useCostStats } from "@/hooks/useCostStats"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import {
  archiveRun,
  attachHistory,
  cancelRun,
  deleteRun,
  fetchActiveRun,
  fetchArtifacts,
  fetchHistory,
  getDefaultReviewConfig,
  resumeRun,
  restoreRun,
  saveLiveRun,
  loadLiveRun,
  clearLiveRun,
  startRun,
  startRunWithMasterlist,
  startRunWithSupplementaryCsv,
} from "@/lib/api"
import { Spinner } from "@/components/ui/feedback"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { HistoryEntry, RunRequest, RunResponse, StoredApiKeys } from "@/lib/api"
import { RunView } from "@/views/RunView"
import type { RunTab, SelectedRun } from "@/views/RunView"

const SetupView = lazy(() => import("@/views/SetupView").then((m) => ({ default: m.SetupView })))

const VALID_TABS = new Set<RunTab>(["activity", "results", "database", "cost", "config", "review-screening", "references"])

// ---------------------------------------------------------------------------
// Top-level error boundary: catches render-time crashes in any child view so
// the app shows a recoverable error UI instead of a blank white screen.
// ---------------------------------------------------------------------------

interface ErrorBoundaryState {
  hasError: boolean
  message: string
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { hasError: false, message: "" }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message || "Unknown error" }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[AppErrorBoundary]", error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen bg-background text-zinc-100 gap-4 p-8">
          <AlertTriangle className="h-10 w-10 text-red-400" />
          <h1 className="text-xl font-semibold text-red-400">Something went wrong</h1>
          <p className="text-zinc-400 text-sm max-w-md text-center">{this.state.message}</p>
          <button
            className="mt-2 px-4 py-2 text-sm rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-100 transition-colors"
            onClick={() => { this.setState({ hasError: false, message: "" }); window.location.href = "/" }}
          >
            Reload app
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function parseRunUrl(pathname: string): { workflowId: string; tab: RunTab } | null {
  const match = pathname.match(/^\/run\/([^/]+)(?:\/([^/]+))?$/)
  if (!match) return null
  const workflowId = match[1]
  const rawTab = match[2] ?? "activity"
  const tab = VALID_TABS.has(rawTab as RunTab) ? (rawTab as RunTab) : "activity"
  return { workflowId, tab }
}

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <Spinner size="md" className="text-violet-500" />
    </div>
  )
}


export default function App() {
  const navigate = useNavigate()
  const location = useLocation()

  // matchMedia is more reliable than window.innerWidth for SSR/hydration safety and
  // avoids reading a stale value before layout has settled.
  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 639px)").matches)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  )
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const stored = localStorage.getItem("sidebar-width")
    return stored ? Math.max(200, Math.min(420, Number(stored))) : 240
  })
  const [defaultYaml, setDefaultYaml] = useState("")

  // --- Live SSE run ---
  const [liveRunId, setLiveRunId] = useState<string | null>(null)
  const [liveTopic, setLiveTopic] = useState<string | null>(null)
  const [liveStartedAt, setLiveStartedAt] = useState<Date | null>(null)

  // --- Selected run (what is displayed in the main area) ---
  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)
  const [activeRunTab, setActiveRunTab] = useState<RunTab>("activity")
  const [submissionFocusTarget, setSubmissionFocusTarget] = useState<"reference-papers" | null>(null)
  const [submissionFocusToken, setSubmissionFocusToken] = useState(0)
  const [resumeLauncherWorkflowId, setResumeLauncherWorkflowId] = useState<string | null>(null)
  const [resumeAutoArmToken, setResumeAutoArmToken] = useState(0)
  const [costOpsOpen, setCostOpsOpen] = useState(false)

  // Artifacts for historical ResultsView
  const [historyOutputs, setHistoryOutputs] = useState<Record<string, string>>({})

  const [liveWorkflowId, setLiveWorkflowId] = useState<string | null>(null)

  // Track the last workflowId we pushed to the URL (avoid duplicate navigations).
  const liveRunNavigatedRef = useRef<string | null>(null)
  // Tracks whether the current live run reached "streaming" state at least once.
  // Used to distinguish truly-live runs (that finished streaming) from runs
  // restored from localStorage that were already finished (prefetch-detected
  // as terminal). Only the former should clear liveRunId from React state.
  const wasStreamingRef = useRef(false)

  const { events, status, abort, reset } = useSSEStream(liveRunId, liveWorkflowId)
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

  // True when the currently viewed run is backed by the active SSE stream.
  // During handoffs, run_id can change before all selectedRun fields settle,
  // so we also allow a workflow_id match when both sides are known.
  const isViewingLiveRun =
    selectedRun !== null &&
    liveRunId !== null &&
    (selectedRun.runId === liveRunId ||
      (Boolean(selectedRun.workflowId) &&
        Boolean(liveWorkflowId) &&
        selectedRun.workflowId === liveWorkflowId))

  // Events to pass to RunView: only provide live events when viewing the live run.
  const viewEvents = isViewingLiveRun ? events : []

  // Sidebar live run descriptor -- memoized to prevent Sidebar re-renders when
  // App.tsx re-renders for unrelated reasons (e.g. selectedRun changes).
  const livePapersFound = useMemo(
    () =>
      events
        .filter((e) => e.type === "connector_result" && e.status === "success")
        .reduce((acc, e) => acc + (e.type === "connector_result" ? (e.records ?? 0) : 0), 0),
    [events],
  )
  const liveIncluded = useMemo(() => {
    const lastDecision = new Map<string, string>()
    for (const e of events) {
      if (e.type === "screening_decision") {
        lastDecision.set(e.paper_id, e.decision)
      }
    }
    return [...lastDecision.values()].filter((d) => d === "include").length
  }, [events])
  const livePhaseProgress = useMemo(() => computePhaseProgress(events), [events])
  const liveFunnelStages = useMemo(() => computeFunnelStages(events), [events])

  const liveRunForSidebar = useMemo<LiveRun | null>(
    () =>
      liveRunId
        ? {
            runId: liveRunId,
            topic: liveTopic ?? "",
            status,
            cost: costStats.total_cost,
            workflowId: liveWorkflowId,
            phaseProgress: livePhaseProgress,
            startedAt: liveStartedAt?.toISOString() ?? null,
            papersFound: livePapersFound > 0 ? livePapersFound : null,
            papersIncluded: liveIncluded > 0 ? liveIncluded : null,
            funnelStages: liveFunnelStages.length > 0 ? liveFunnelStages : undefined,
          }
        : null,
    // livePhaseProgress and liveFunnelStages intentionally included; they memoize
    // derived event data so the sidebar object only updates when values actually change.
    [liveRunId, liveTopic, status, costStats.total_cost, liveWorkflowId, livePhaseProgress, liveStartedAt, livePapersFound, liveIncluded, liveFunnelStages],
  )

  // ---------------------------------------------------------------------------
  // Restore a historical run from the URL (direct navigation / refresh).
  // The `isAborted` callback lets the mount effect cancel stale calls when
  // React StrictMode double-invokes the effect (mount -> cleanup -> mount).
  // ---------------------------------------------------------------------------
  async function restoreRunFromUrl(workflowId: string, tab: RunTab, isAborted?: () => boolean) {
    try {
      const history = await fetchHistory()
      if (isAborted?.()) return
      const entry = history.find((e) => e.workflow_id === workflowId)
      if (!entry) {
        navigate("/", { replace: true })
        return
      }
      // If the workflow has an in-process active task, connect SSE directly.
      if (entry.live_run_id) {
        if (isAborted?.()) return
        const now = new Date()
        reset()
        liveRunNavigatedRef.current = workflowId
        setLiveRunId(entry.live_run_id)
        setLiveTopic(entry.topic)
        setLiveStartedAt(now)
        setLiveWorkflowId(workflowId)
        saveLiveRun({ runId: entry.live_run_id, topic: entry.topic, startedAt: now.toISOString(), workflowId })
        setSelectedRun({
          runId: entry.live_run_id,
          workflowId,
          topic: entry.topic,
          dbPath: entry.db_path || null,
          isDone: false,
          startedAt: now,
          createdAt: entry.created_at,
        })
        setActiveRunTab(tab)
        return
      }
      const res = await attachHistory(entry)
      if (isAborted?.()) return
      const isCompleted = ["completed", "done", "stale", "interrupted", "cancelled", "failed", "error"].includes(
        entry.status.toLowerCase(),
      )
      setSelectedRun({
        runId: res.run_id,
        workflowId: entry.workflow_id,
        topic: entry.topic,
        dbPath: entry.db_path,
        isDone: isCompleted,
        historicalStatus: entry.status,
        startedAt: null,
        createdAt: entry.created_at,
        papersFound: entry.papers_found ?? null,
        papersIncluded: entry.papers_included ?? null,
        historicalCost: entry.total_cost ?? null,
      })
      setActiveRunTab(tab)
    } catch {
      if (!isAborted?.()) navigate("/", { replace: true })
    }
  }

  // ---------------------------------------------------------------------------
  // Mount: restore live SSE state from localStorage AND restore selectedRun from URL
  // ---------------------------------------------------------------------------
  useEffect(() => {
    // Track whether this effect invocation was superseded (React StrictMode
    // double-invokes effects: mount -> cleanup -> mount). Setting `aborted = true`
    // in the cleanup cancels any in-flight async work from the first invocation
    // so the second invocation starts fresh without duplicate API calls.
    let aborted = false

    const stored = loadLiveRun()

    // Always reconnect SSE state from localStorage if available.
    if (stored) {
      setLiveRunId(stored.runId)
      setLiveTopic(stored.topic)
      setLiveStartedAt(new Date(stored.startedAt))
      if (stored.workflowId) {
        setLiveWorkflowId(stored.workflowId)
        liveRunNavigatedRef.current = stored.workflowId
      }
    }

    // Restore selectedRun and active tab from the URL.
    const parsed = parseRunUrl(location.pathname)
    if (!parsed) return // URL is "/", show SetupView

    const { workflowId: urlWfId, tab: urlTab } = parsed
    setActiveRunTab(urlTab)

    if (stored?.workflowId === urlWfId) {
      // URL points to the currently-live run in localStorage. Probe backend
      // first to avoid trusting stale run_ids after restart/resume.
      void (async () => {
        const active = await fetchActiveRun(urlWfId)
        if (aborted) return

        if (active && active.run_id === stored.runId) {
          setSelectedRun({
            runId: stored.runId,
            workflowId: stored.workflowId ?? null,
            topic: stored.topic,
            dbPath: null,
            isDone: false,
            startedAt: new Date(stored.startedAt),
            createdAt: stored.startedAt,
          })
          return
        }

        // Stale local run state: clear and restore from registry/attach flow.
        clearLiveRun()
        setLiveRunId(null)
        setLiveWorkflowId(null)
        setLiveTopic(null)
        setLiveStartedAt(null)
        void restoreRunFromUrl(urlWfId, urlTab, () => aborted)
      })()
    } else {
      // URL points to a historical run -- load from the history API.
      void restoreRunFromUrl(urlWfId, urlTab, () => aborted)
    }

    return () => {
      aborted = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- mount only

  // ---------------------------------------------------------------------------
  // Clear live run state when the run finishes. Two cases are handled:
  //
  // 1. Run was actually streaming (wasStreamingRef = true): clear localStorage
  //    only. Do NOT clear React state -- the liveRun card stays at the top of
  //    the sidebar showing the final status (Completed/Error/Cancelled). The
  //    user sees their result immediately without a registry-update race
  //    condition. The card is replaced when a new run starts.
  //
  // 2. Run was prefetch-detected as already-finished (wasStreamingRef = false,
  //    e.g. page reload where localStorage points to a previously-cancelled
  //    run that never streamed in this session): clear both localStorage AND
  //    React state so the zombie card is removed from the top of the sidebar.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (status === "streaming") {
      wasStreamingRef.current = true
    }
    if (status === "done" || status === "error" || status === "cancelled") {
      clearLiveRun()
      if (!wasStreamingRef.current) {
        // Prefetch-detected terminal: remove the stale card from the UI.
        setLiveRunId(null)
        setLiveWorkflowId(null)
      }
      // If wasStreamingRef = true (was live): keep React state so the card
      // persists at top. wasStreamingRef resets when the next run starts.
      wasStreamingRef.current = false
    }
  }, [status])

  // ---------------------------------------------------------------------------
  // Sync selectedRun.workflowId from liveOutputs (run "done" event).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!liveOutputs || !liveRunId) return
    const wfId = liveOutputs.workflow_id as string | undefined
    if (wfId && selectedRun?.runId === liveRunId && !selectedRun?.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: wfId, isDone: true } : r))
      setLiveWorkflowId(wfId)
      const stored = loadLiveRun()
      if (stored) saveLiveRun({ ...stored, workflowId: wfId })
    }
  }, [liveOutputs, liveRunId, selectedRun])

  // ---------------------------------------------------------------------------
  // Eagerly populate workflowId from workflow_id_ready SSE event, then navigate.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!liveWorkflowId || !liveRunId) return

    // Keep selectedRun.workflowId in sync.
    if (selectedRun?.runId === liveRunId && !selectedRun?.workflowId) {
      setSelectedRun((r) => (r ? { ...r, workflowId: liveWorkflowId } : r))
    }

    // Navigate to /run/:workflowId/:tab the first time we learn the workflowId
    // for this live run. Subsequent tab changes use handleTabChange instead.
    if (liveRunNavigatedRef.current !== liveWorkflowId) {
      liveRunNavigatedRef.current = liveWorkflowId
      if (!selectedRun || selectedRun.runId === liveRunId) {
        navigate(`/run/${liveWorkflowId}/${activeRunTab}`, { replace: true })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- activeRunTab and navigate are stable; intentionally excluded
  }, [liveWorkflowId, liveRunId, selectedRun?.runId, selectedRun?.workflowId])

  // ---------------------------------------------------------------------------
  // Pick up workflow_id_ready SSE event (fires earlier than the "done" event).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (liveWorkflowId) return
    const ev = events.find((e) => e.type === "workflow_id_ready")
    if (!ev || ev.type !== "workflow_id_ready") return
    const wfId = ev.workflow_id
    if (wfId) {
      setLiveWorkflowId(wfId)
      const stored = loadLiveRun()
      if (stored) saveLiveRun({ ...stored, workflowId: wfId })
    }
  }, [events, liveWorkflowId])

  // ---------------------------------------------------------------------------
  // Load default YAML config.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    getDefaultReviewConfig()
      .then((yaml) => setDefaultYaml(yaml))
      .catch(() => {})
  }, [isOnline])

  // ---------------------------------------------------------------------------
  // Fetch artifacts for ResultsView when viewing a completed historical run.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!selectedRun?.isDone || isViewingLiveRun) {
      setHistoryOutputs({})
      return
    }
    fetchArtifacts(selectedRun.runId)
      .then((artifacts) => setHistoryOutputs(artifacts))
      .catch(() => setHistoryOutputs({}))
  }, [selectedRun?.runId, selectedRun?.isDone, isViewingLiveRun])

  // ---------------------------------------------------------------------------
  // Poll for CLI-initiated resume: when viewing a run, check if it became active.
  // Stops automatically after 10 consecutive 404s (~8s) to prevent log spam.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const wfId = selectedRun?.workflowId
    const isTerminalHistory =
      selectedRun?.historicalStatus != null &&
      ["cancelled", "done", "completed", "interrupted", "stale"].includes(
        selectedRun.historicalStatus.toLowerCase(),
      )
    if (!wfId || isViewingLiveRun || isTerminalHistory) return
    const workflowId = wfId

    let consecutiveMisses = 0
    const MAX_MISSES = 10
    // Guard: stop polling as soon as we successfully switch to live mode.
    // Without this, the interval keeps calling reset()+setLiveRunId() every
    // 800ms even after a successful switch, causing the event log to flicker.
    let switched = false

    async function checkAndSwitch() {
      if (switched) return
      const res = await fetchActiveRun(workflowId)
      if (!res) {
        consecutiveMisses++
        return
      }
      if (liveRunId === res.run_id && selectedRun?.runId === res.run_id) {
        switched = true
        return
      }
      // Mark as switched immediately so concurrent/delayed callbacks are no-ops.
      switched = true
      consecutiveMisses = 0
      setResumeLauncherWorkflowId(null)
      const now = new Date()
      reset()
      liveRunNavigatedRef.current = null
      setLiveRunId(res.run_id)
      setLiveTopic(res.topic)
      setLiveStartedAt(now)
      setLiveWorkflowId(workflowId)
      saveLiveRun({ runId: res.run_id, topic: res.topic, startedAt: now.toISOString(), workflowId })
      setSelectedRun({
        runId: res.run_id,
        workflowId,
        topic: res.topic,
        dbPath: null,
        isDone: false,
        startedAt: now,
        createdAt: now.toISOString(),
      })
      setActiveRunTab("activity")
      navigate(`/run/${workflowId}/activity`, { replace: true })
    }

    void checkAndSwitch()
    const interval = setInterval(() => {
      if (switched || consecutiveMisses >= MAX_MISSES) {
        clearInterval(interval)
        return
      }
      void checkAndSwitch()
    }, 800)

    return () => clearInterval(interval)
  }, [selectedRun?.workflowId, selectedRun?.historicalStatus, selectedRun?.runId, liveRunId, isViewingLiveRun, reset, navigate])

  // ---------------------------------------------------------------------------
  // Track mobile viewport (< 640px) and auto-collapse sidebar on mobile.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)")
    function handleChange(e: MediaQueryListEvent) {
      setIsMobile(e.matches)
      if (e.matches) setSidebarCollapsed(true)
    }
    mq.addEventListener("change", handleChange)
    return () => mq.removeEventListener("change", handleChange)
  }, [])

  // ---------------------------------------------------------------------------
  // Keyboard shortcut: Cmd+B / Ctrl+B to toggle sidebar
  // ---------------------------------------------------------------------------
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
    setResumeLauncherWorkflowId(null)
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = null
    const now = new Date()
    const res = await startRun(req)
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    setLiveWorkflowId(null)
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
    // URL will update once workflow_id_ready fires and liveWorkflowId is set.
  }

  async function handleStartWithSupplementaryCsv(csvFile: File, req: RunRequest) {
    setResumeLauncherWorkflowId(null)
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = null
    const now = new Date()
    const keys: StoredApiKeys = {
      gemini: req.gemini_api_key,
      openalex: req.openalex_api_key ?? "",
      ieee: req.ieee_api_key ?? "",
      pubmedEmail: req.pubmed_email ?? "",
      pubmedApiKey: req.pubmed_api_key ?? "",
      perplexity: req.perplexity_api_key ?? "",
      semanticScholar: req.semantic_scholar_api_key ?? "",
      crossrefEmail: req.crossref_email ?? "",
      wos: req.wos_api_key ?? "",
      scopus: req.scopus_api_key ?? "",
    }
    const res = await startRunWithSupplementaryCsv(csvFile, req.review_yaml, keys, req.run_root)
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    setLiveWorkflowId(null)
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
  }

  async function handleStartWithMasterlistCsv(csvFile: File, req: RunRequest) {
    setResumeLauncherWorkflowId(null)
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = null
    const now = new Date()
    const keys: StoredApiKeys = {
      gemini: req.gemini_api_key,
      openalex: req.openalex_api_key ?? "",
      ieee: req.ieee_api_key ?? "",
      pubmedEmail: req.pubmed_email ?? "",
      pubmedApiKey: req.pubmed_api_key ?? "",
      perplexity: req.perplexity_api_key ?? "",
      semanticScholar: req.semantic_scholar_api_key ?? "",
      crossrefEmail: req.crossref_email ?? "",
      wos: req.wos_api_key ?? "",
      scopus: req.scopus_api_key ?? "",
    }
    const res = await startRunWithMasterlist(csvFile, req.review_yaml, keys, req.run_root)
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    setLiveWorkflowId(null)
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
  }

  async function handleCancel() {
    if (liveRunId) await cancelRun(liveRunId)
    abort()
  }

  function handleNewReview() {
    setResumeLauncherWorkflowId(null)
    setSelectedRun(null)
    setHistoryOutputs({})
    navigate("/")
  }

  function handleSelectLiveRun() {
    if (!liveRunId || !liveTopic) return
    setResumeLauncherWorkflowId(null)
    setSelectedRun({
      runId: liveRunId,
      workflowId: liveWorkflowId,
      topic: liveTopic,
      dbPath: null,
      isDone: status === "done" || status === "error" || status === "cancelled",
      startedAt: liveStartedAt,
      createdAt: liveStartedAt?.toISOString() ?? null,
    })
    if (liveWorkflowId) {
      navigate(`/run/${liveWorkflowId}/activity`)
    }
  }

  async function handleSelectHistory(entry: HistoryEntry) {
    setResumeLauncherWorkflowId(null)
    const focusSelectedWorkflow = () => {
      setActiveRunTab("activity")
      navigate(`/run/${entry.workflow_id}/activity`, { replace: true })
    }
    // Always probe the backend for an active run first. Sidebar history can lag
    // briefly after CLI resume and miss live_run_id on a running workflow.
    const active = await fetchActiveRun(entry.workflow_id).catch(() => null)
    if (active) {
      if (
        isSameRunSelection(
          liveRunId,
          selectedRun?.runId,
          selectedRun?.workflowId,
          active.run_id,
          entry.workflow_id,
        )
      ) {
        focusSelectedWorkflow()
        return
      }
      const now = new Date()
      if (liveRunId !== active.run_id) {
        reset()
      }
      liveRunNavigatedRef.current = entry.workflow_id
      setLiveRunId(active.run_id)
      setLiveTopic(active.topic || entry.topic)
      setLiveStartedAt(now)
      setLiveWorkflowId(entry.workflow_id)
      saveLiveRun({
        runId: active.run_id,
        topic: active.topic || entry.topic,
        startedAt: now.toISOString(),
        workflowId: entry.workflow_id,
      })
      setSelectedRun({
        runId: active.run_id,
        workflowId: entry.workflow_id,
        topic: active.topic || entry.topic,
        dbPath: entry.db_path || null,
        isDone: false,
        startedAt: now,
        createdAt: entry.created_at,
      })
      focusSelectedWorkflow()
      return
    }
    // If the workflow has an in-process active task, connect live SSE directly
    // instead of replaying stale DB events.
    if (entry.live_run_id) {
      if (
        isSameRunSelection(
          liveRunId,
          selectedRun?.runId,
          selectedRun?.workflowId,
          entry.live_run_id,
          entry.workflow_id,
        )
      ) {
        focusSelectedWorkflow()
        return
      }
      const now = new Date()
      if (liveRunId !== entry.live_run_id) {
        reset()
      }
      liveRunNavigatedRef.current = entry.workflow_id
      setLiveRunId(entry.live_run_id)
      setLiveTopic(entry.topic)
      setLiveStartedAt(now)
      setLiveWorkflowId(entry.workflow_id)
      saveLiveRun({ runId: entry.live_run_id, topic: entry.topic, startedAt: now.toISOString(), workflowId: entry.workflow_id })
      setSelectedRun({
        runId: entry.live_run_id,
        workflowId: entry.workflow_id,
        topic: entry.topic,
        dbPath: entry.db_path || null,
        isDone: false,
        startedAt: now,
        createdAt: entry.created_at,
      })
      focusSelectedWorkflow()
      return
    }
    // Historical run: replay events from DB.
    const res = await attachHistory(entry)
    const isCompleted = ["completed", "done", "stale", "interrupted", "cancelled", "failed", "error"].includes(entry.status.toLowerCase())
    setSelectedRun({
      runId: res.run_id,
      workflowId: entry.workflow_id,
      topic: entry.topic,
      dbPath: entry.db_path,
      isDone: isCompleted,
      historicalStatus: entry.status,
      startedAt: null,
      createdAt: entry.created_at,
      papersFound: entry.papers_found ?? null,
      papersIncluded: entry.papers_included ?? null,
      historicalCost: entry.total_cost ?? null,
    })
    navigate(`/run/${entry.workflow_id}/activity`)
  }

  function handleGoHome() {
    setResumeLauncherWorkflowId(null)
    setSelectedRun(null)
    navigate("/")
  }

  function handleResumeRun(res: RunResponse, workflowId: string) {
    setResumeLauncherWorkflowId(null)
    const now = new Date()
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = workflowId
    setLiveRunId(res.run_id)
    setLiveTopic(res.topic)
    setLiveStartedAt(now)
    setLiveWorkflowId(workflowId)
    saveLiveRun({ runId: res.run_id, topic: res.topic, startedAt: now.toISOString(), workflowId })
    const run: SelectedRun = {
      runId: res.run_id,
      workflowId,
      topic: res.topic,
      dbPath: null,
      isDone: false,
      startedAt: now,
      createdAt: now.toISOString(),
    }
    setSelectedRun(run)
    setActiveRunTab("activity")
    navigate(`/run/${workflowId}/activity`, { replace: true })
  }

  function selectedRunToHistoryEntry(): HistoryEntry | null {
    if (!selectedRun?.workflowId || !selectedRun.dbPath) return null
    return {
      workflow_id: selectedRun.workflowId,
      topic: selectedRun.topic,
      status: selectedRun.historicalStatus ?? "stale",
      db_path: selectedRun.dbPath,
      created_at: selectedRun.createdAt ?? new Date().toISOString(),
      papers_found: selectedRun.papersFound ?? null,
      papers_included: selectedRun.papersIncluded ?? null,
      total_cost: selectedRun.historicalCost ?? null,
      live_run_id: null,
      notes: null,
    }
  }

  async function executeTimelineResume(fromPhase?: string | null) {
    const entry = selectedRunToHistoryEntry()
    if (!entry) return
    try {
      const res = await resumeRun(entry, fromPhase)
      handleResumeRun(res, entry.workflow_id)
      if (fromPhase) {
        toast.success("Resumed from selected phase")
      } else {
        toast.success("Resumed from last checkpoint")
      }
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error)
      if (msg.includes("400")) {
        toast.error("Invalid resume phase. Try a different phase.")
      } else if (msg.includes("409")) {
        toast.error("Workflow already running. Open live run or stop it before resuming.")
      } else {
        toast.error(msg || "Failed to resume run")
      }
      throw error
    }
  }

  async function handleSidebarResumeLauncher(entry: HistoryEntry) {
    await handleSelectHistory(entry)
    setResumeLauncherWorkflowId(entry.workflow_id)
    setResumeAutoArmToken((v) => v + 1)
    setActiveRunTab("activity")
    navigate(`/run/${entry.workflow_id}/activity`, { replace: true })
  }

  async function handleTimelineResumePhase(phase: string) {
    await executeTimelineResume(phase)
  }

  async function handleSidebarDelete(workflowId: string) {
    await deleteRun(workflowId)
    if (selectedRun?.workflowId === workflowId) {
      setSelectedRun(null)
      navigate("/", { replace: true })
    }
  }

  async function handleSidebarArchive(workflowId: string) {
    await archiveRun(workflowId)
    if (selectedRun?.workflowId === workflowId) {
      setSelectedRun(null)
      navigate("/", { replace: true })
    }
  }

  async function handleSidebarRestore(workflowId: string) {
    await restoreRun(workflowId)
  }

  function handleSidebarWidthChange(w: number) {
    setSidebarWidth(w)
    localStorage.setItem("sidebar-width", String(w))
  }

  // Update URL when the active tab changes.
  function handleTabChange(tab: RunTab) {
    setActiveRunTab(tab)
    if (tab !== "results") setSubmissionFocusTarget(null)
    if (selectedRun?.workflowId) {
      navigate(`/run/${selectedRun.workflowId}/${tab}`, { replace: true })
    }
  }

  function handleGoToSubmissionReferencePapers() {
    setSubmissionFocusTarget("reference-papers")
    setSubmissionFocusToken((v) => v + 1)
    setActiveRunTab("results")
    if (selectedRun?.workflowId) {
      navigate(`/run/${selectedRun.workflowId}/results`, { replace: true })
    }
  }

  function handleOpenCostOps() {
    setCostOpsOpen(true)
  }

  // ---------------------------------------------------------------------------
  // Layout
  // ---------------------------------------------------------------------------

  // On mobile the sidebar is an overlay (drawer), so it does not push content.
  const mainMargin = isMobile ? 0 : sidebarCollapsed ? 56 : sidebarWidth

  function renderMain() {
    if (selectedRun === null) {
      return (
        <Suspense fallback={<ViewLoader />}>
          <SetupView
            defaultReviewYaml={defaultYaml}
            onSubmit={handleStart}
            onSubmitWithSupplementaryCsv={handleStartWithSupplementaryCsv}
            onSubmitWithMasterlistCsv={handleStartWithMasterlistCsv}
            disabled={isRunning}
          />
        </Suspense>
      )
    }

    // Map the registry's raw status string to an SSE-style status for historical runs.
    const resolvedHistoricalStatus = (() => {
      const s = (selectedRun.historicalStatus ?? "completed").toLowerCase()
      if (s === "completed" || s === "done") return "done"
      if (s === "running" || s === "streaming") return "streaming"
      if (s === "awaiting_review") return "awaiting_review"
      if (s === "stale") return "error"
      if (s === "failed" || s === "error") return "error"
      if (s === "cancelled" || s === "canceled") return "cancelled"
      if (s === "interrupted") return "cancelled"
      return "done"
    })()
    const completedHistoricalRun =
      !isViewingLiveRun &&
      ["completed", "done"].includes((selectedRun.historicalStatus ?? "").toLowerCase())
    const resumeModeActive =
      !isViewingLiveRun &&
      (selectedRun?.workflowId === resumeLauncherWorkflowId || completedHistoricalRun)

    return (
      <RunView
        run={selectedRun}
        events={viewEvents}
        isViewingLiveRun={isViewingLiveRun}
        status={isViewingLiveRun ? status : resolvedHistoricalStatus}
        costStats={isViewingLiveRun ? costStats : { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] }}
        activeTab={activeRunTab}
        onTabChange={handleTabChange}
        onGoToSubmissionReferencePapers={handleGoToSubmissionReferencePapers}
        onCancel={handleCancel}
        historyOutputs={historyOutputs}
        liveOutputs={isViewingLiveRun ? liveOutputs : {}}
        dbUnlocked={Boolean(dbUnlocked)}
        isLive={isViewingLiveRun && isRunning && Boolean(dbUnlocked)}
        onResumeFromPhase={!isViewingLiveRun ? handleTimelineResumePhase : undefined}
        resumeModeActive={resumeModeActive}
        autoArmFromSidebarToken={resumeAutoArmToken}
        submissionFocusTarget={submissionFocusTarget}
        submissionFocusToken={submissionFocusToken}
      />
    )
  }

  // Breadcrumb
  const breadcrumbTopic = selectedRun?.topic ?? null
  const breadcrumbTab = selectedRun
    ? activeRunTab.charAt(0).toUpperCase() + activeRunTab.slice(1)
    : "New Review"

  async function handleCopyTopic() {
    if (!breadcrumbTopic) return
    try {
      await navigator.clipboard.writeText(breadcrumbTopic)
      toast.success("Copied!")
    } catch {
      toast.error("Failed to copy")
    }
  }

  return (
    <div className="flex h-dvh bg-background text-zinc-100 overflow-hidden">
      <Toaster position="top-center" richColors closeButton />
      <Sidebar
        liveRun={liveRunForSidebar}
        selectedWorkflowId={selectedRun?.workflowId ?? null}
        isLiveRunSelected={isViewingLiveRun}
        onSelectLiveRun={handleSelectLiveRun}
        onSelectHistory={(entry) => void handleSelectHistory(entry)}
        onNewReview={handleNewReview}
        onResume={handleSidebarResumeLauncher}
        onArchive={handleSidebarArchive}
        onRestore={handleSidebarRestore}
        onDelete={handleSidebarDelete}
        onCancel={handleCancel}
        isRunning={isRunning}
        onGoHome={handleGoHome}
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        width={sidebarWidth}
        onWidthChange={handleSidebarWidthChange}
        isMobile={isMobile}
      />

      <main
        className="relative isolate flex-1 h-full overflow-hidden overscroll-none flex flex-col transition-[margin-left] duration-200 ease-in-out"
        style={{ marginLeft: mainMargin }}
      >
        {/* Ambient warm glow behind glass content (subtle orange balance to sidebar violet) */}
        <div
          className="pointer-events-none absolute inset-0 z-0"
          aria-hidden
          style={{
            background:
              "radial-gradient(52% 38% at 82% 14%, rgb(251 146 60 / var(--ambient-orange-alpha)) 0%, rgb(251 146 60 / var(--ambient-orange-alpha-soft)) 34%, transparent 74%), radial-gradient(46% 34% at 10% 18%, rgb(139 92 246 / 0.06) 0%, rgb(139 92 246 / 0.02) 44%, transparent 72%)",
          }}
        />
        {/* Top bar -- paddingTop pushes content below the iOS status bar when viewport-fit=cover is active */}
        <header
          className="sticky top-0 z-30 glass-toolbar border-b border-zinc-800/70 shrink-0"
          style={{ paddingTop: 'env(safe-area-inset-top)' }}
        >
          <div className="h-14 flex items-center px-4 gap-3">
            {/* Hamburger: only visible on mobile to open the sidebar drawer */}
            {isMobile && (
              <button
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Open menu"
                className="flex items-center justify-center h-10 w-10 -ml-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors shrink-0"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            {/* Breadcrumb */}
            <TooltipProvider delayDuration={0}>
              <div className="flex items-center gap-1.5 text-sm flex-1 min-w-0">
                {breadcrumbTopic ? (
                  <>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => void handleCopyTopic()}
                          className="text-zinc-400 font-medium truncate flex-1 min-w-0 text-left hover:text-zinc-200 transition-colors cursor-pointer"
                        >
                          {breadcrumbTopic}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent
                        side="bottom"
                        className="max-w-md break-words bg-zinc-800 border-zinc-700 text-zinc-200"
                      >
                        {breadcrumbTopic}
                      </TooltipContent>
                    </Tooltip>
                    <span className="text-zinc-700 shrink-0">/</span>
                    <span className="text-zinc-300 font-medium shrink-0">{breadcrumbTab}</span>
                  </>
                ) : (
                  <span className="text-zinc-300 font-medium">{breadcrumbTab}</span>
                )}
              </div>
            </TooltipProvider>
          </div>
        </header>

        {/* Backend offline banner */}
        {!isOnline && (
          <div className="flex items-center gap-2.5 bg-amber-500/10 border-b border-amber-500/20 px-6 py-2.5 text-xs text-amber-400 shrink-0">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span className="font-medium">Backend offline.</span>
            <span className="text-amber-500/70">
              Start it with:{" "}
              <code className="font-mono bg-amber-500/10 px-1 py-0.5 rounded">
                pm2 start ecosystem.config.js
              </code>
            </span>
          </div>
        )}

        {/* Main content */}
        <div
          className={
            selectedRun !== null
              ? "relative z-0 flex-1 overflow-hidden"
              : "relative z-0 flex-1 overflow-y-auto p-6"
          }
        >
          {renderMain()}
        </div>

        <button
          type="button"
          onClick={handleOpenCostOps}
          className="fixed bottom-4 right-4 z-40 inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-900/95 px-4 py-2 text-xs font-medium text-zinc-100 shadow-lg hover:bg-zinc-800 transition-colors"
          aria-label="Open costs view"
          title="Open Costs"
        >
          <BarChart3 className="h-3.5 w-3.5" />
          Costs
        </button>
        <GlobalCostOpsDialog open={costOpsOpen} onOpenChange={setCostOpsOpen} />
      </main>
    </div>
  )
}
