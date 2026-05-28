import { useEffect, useMemo, useRef, useState, Suspense, lazy, Component } from "react"
import type { ReactNode, ErrorInfo } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { Toaster, toast } from "sonner"
import { AlertTriangle, Menu, Settings } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import type { LiveRun } from "@/components/Sidebar"
import { SettingsDialog } from "@/components/SettingsDialog"
import { computePhaseProgress } from "@/lib/phaseProgress"
import { computeFunnelStages } from "@/lib/funnelStages"
import {
  isSameRunSelection,
  isSameWorkflowSelection,
  isTerminalHistoricalStatus,
} from "@/lib/runSelection"
import { useSSEStream } from "@/hooks/useSSEStream"
import { useCostStats } from "@/hooks/useCostStats"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import {
  APIResponseError,
  archiveRun,
  attachHistory,
  cancelRun,
  hideCompletedRun,
  deleteRun,
  fetchActiveRun,
  fetchArtifacts,
  fetchHistory,
  buildRunRequest,
  generateConfigStream,
  getDefaultReviewConfig,
  resolveStoredApiKeys,
  resumeRun,
  restoreCompletedRun,
  restoreRun,
  saveLiveRun,
  loadLiveRun,
  clearLiveRun,
  startRun,
  startRunWithMasterlist,
  startRunWithSupplementaryCsv,
} from "@/lib/api"
import { Spinner } from "@/components/ui/feedback"
import { resolveRunStatus } from "@/lib/constants"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { HistoryEntry, RunRequest, RunResponse, StoredApiKeys } from "@/lib/api"
import { RunView } from "@/views/RunView"
import type { RunTab, SelectedRun } from "@/views/RunView"
import type { ConfigGenerateRequest } from "@/views/SetupView"

const SetupView = lazy(() => import("@/views/SetupView").then((m) => ({ default: m.SetupView })))

const VALID_TABS = new Set<RunTab>(["activity", "results", "database", "cost", "config", "quality", "review-screening", "references"])

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
        <div className="flex flex-col items-center justify-center h-screen bg-background text-foreground gap-4 p-8">
          <AlertTriangle className="h-10 w-10 text-intent-danger" />
          <h1 className="text-xl font-semibold text-intent-danger">Something went wrong</h1>
          <p className="text-muted text-sm max-w-md text-center">{this.state.message}</p>
          <button
            className="mt-2 px-4 py-2 text-sm rounded bg-surface-2 hover:bg-surface-3 text-foreground transition-colors"
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

interface DraftConfigState {
  request: ConfigGenerateRequest | null
  yaml: string
  isGenerating: boolean
  activeStep: string
  stepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
  generationError: string | null
}

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-48">
      <Spinner size="md" />
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
  const [draftConfig, setDraftConfig] = useState<DraftConfigState | null>(null)
  const [submissionFocusTarget, setSubmissionFocusTarget] = useState<"reference-papers" | null>(null)
  const [submissionFocusToken, setSubmissionFocusToken] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)

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
  const { isOnline } = useBackendHealth(6000, { suppressOffline: status === "streaming" })

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

  function clearLiveRunUi() {
    clearLiveRun()
    reset()
    setLiveRunId(null)
    setLiveWorkflowId(null)
    setLiveTopic(null)
    setLiveStartedAt(null)
    wasStreamingRef.current = false
  }

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
      clearLiveRunUi()
      const isCompleted = isTerminalHistoricalStatus(entry.status)
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
    if (urlWfId === "draft") {
      // Draft routing is session-local state; refresh should return to setup.
      navigate("/", { replace: true })
      return
    }

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
    const run = selectedRun
    if (!run?.isDone || isViewingLiveRun || run.attachPending) {
      setHistoryOutputs({})
      return
    }
    if (run.historicalStatus && !isTerminalHistoricalStatus(run.historicalStatus)) {
      setHistoryOutputs({})
      return
    }
    fetchArtifacts(run.runId, { workflowIdFallback: run.workflowId })
      .then((artifacts) => setHistoryOutputs(artifacts))
      .catch((err: unknown) => {
        if (err instanceof APIResponseError && err.status === 404) {
          setHistoryOutputs({})
          return
        }
        setHistoryOutputs({})
      })
  }, [
    selectedRun?.runId,
    selectedRun?.workflowId,
    selectedRun?.isDone,
    selectedRun?.attachPending,
    selectedRun?.historicalStatus,
    isViewingLiveRun,
  ])

  // ---------------------------------------------------------------------------
  // Poll for CLI-initiated resume: when viewing a run, check if it became active.
  // Stops automatically after 10 consecutive 404s (~8s) to prevent log spam.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const wfId = selectedRun?.workflowId
    const isTerminalHistory = isTerminalHistoricalStatus(selectedRun?.historicalStatus)
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

  function openDraftRunShell(topic: string) {
    const now = new Date()
    setSelectedRun({
      runId: "draft",
      workflowId: "draft",
      topic,
      dbPath: null,
      isDone: false,
      startedAt: now,
      createdAt: now.toISOString(),
    })
    setActiveRunTab("config")
    navigate("/run/draft/config", { replace: true })
  }

  async function handleStartDraftConfig(req: ConfigGenerateRequest) {
    openDraftRunShell(req.question)
    setDraftConfig({
      request: req,
      yaml: "",
      isGenerating: true,
      activeStep: "start",
      stepMetadata: {},
      usedWebFallback: false,
      fallbackReason: null,
      generationError: null,
    })
    try {
      const yaml = await generateConfigStream(
        req.question,
        req.deepseekKey,
        req.generationProfile,
        (step, metadata) => {
          const normalizedStep = step === "structuring_retry" ? "structuring" : step
          setDraftConfig((prev) => {
            if (!prev) return prev
            const reason = step === "web_research_fallback" && typeof metadata?.reason === "string"
              ? metadata.reason
              : prev.fallbackReason
            return {
              ...prev,
              activeStep: normalizedStep,
              stepMetadata: metadata ?? {},
              usedWebFallback: prev.usedWebFallback || step === "web_research_fallback",
              fallbackReason: reason,
            }
          })
        },
      )
      setDraftConfig((prev) => (prev ? { ...prev, yaml, isGenerating: false, generationError: null } : prev))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setDraftConfig((prev) => (prev ? { ...prev, isGenerating: false, generationError: message } : prev))
    }
  }

  function handleOpenDraftYaml(yaml: string) {
    openDraftRunShell("Draft config")
    setDraftConfig({
      request: null,
      yaml,
      isGenerating: false,
      activeStep: "finalizing",
      stepMetadata: {},
      usedWebFallback: false,
      fallbackReason: null,
      generationError: null,
    })
  }

  async function handleRetryDraftConfigGeneration() {
    if (!draftConfig?.request) return
    await handleStartDraftConfig(draftConfig.request)
  }

  async function handleLaunchDraftConfig(yaml: string) {
    if (!draftConfig?.request) return
    const req = buildRunRequest(
      yaml,
      resolveStoredApiKeys({ deepseek: draftConfig.request.deepseekKey }),
    )
    setDraftConfig(null)
    if (draftConfig.request.csvFile && draftConfig.request.csvMode === "masterlist") {
      await handleStartWithMasterlistCsv(draftConfig.request.csvFile, req)
      return
    }
    if (draftConfig.request.csvFile) {
      await handleStartWithSupplementaryCsv(draftConfig.request.csvFile, req)
      return
    }
    await handleStart(req)
  }

  async function handleStart(req: RunRequest) {
    setDraftConfig(null)
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
    setDraftConfig(null)
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = null
    const now = new Date()
    const keys: StoredApiKeys = {
      gemini: req.gemini_api_key ?? "",
      deepseek: req.deepseek_api_key,
      openrouter: req.openrouter_api_key ?? "",
      openai: req.openai_api_key ?? "",
      anthropic: req.anthropic_api_key ?? "",
      groq: req.groq_api_key ?? "",
      mistral: req.mistral_api_key ?? "",
      cohere: req.cohere_api_key ?? "",
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
    setDraftConfig(null)
    reset()
    wasStreamingRef.current = false
    liveRunNavigatedRef.current = null
    const now = new Date()
    const keys: StoredApiKeys = {
      gemini: req.gemini_api_key ?? "",
      deepseek: req.deepseek_api_key,
      openrouter: req.openrouter_api_key ?? "",
      openai: req.openai_api_key ?? "",
      anthropic: req.anthropic_api_key ?? "",
      groq: req.groq_api_key ?? "",
      mistral: req.mistral_api_key ?? "",
      cohere: req.cohere_api_key ?? "",
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
    setDraftConfig(null)
    setSelectedRun(null)
    setHistoryOutputs({})
    navigate("/")
  }

  function handleSelectLiveRun() {
    if (!liveRunId || !liveTopic) return
    setDraftConfig(null)
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
    setDraftConfig(null)
    const focusSelectedWorkflow = () => {
      setActiveRunTab("activity")
      navigate(`/run/${entry.workflow_id}/activity`, { replace: true })
    }

    if (isSameWorkflowSelection(selectedRun?.workflowId, entry.workflow_id)) {
      focusSelectedWorkflow()
      return
    }

    const terminalHistorical =
      isTerminalHistoricalStatus(entry.status) && !entry.live_run_id

    if (terminalHistorical) {
      clearLiveRunUi()
      const isCompleted = isTerminalHistoricalStatus(entry.status)
      setSelectedRun({
        runId: entry.workflow_id,
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
        attachPending: true,
      })
      focusSelectedWorkflow()
      try {
        const res = await attachHistory(entry)
        setSelectedRun((current) =>
          current?.workflowId === entry.workflow_id
            ? { ...current, runId: res.run_id, attachPending: false }
            : current,
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        toast.error(`Could not open run: ${msg}`)
      }
      return
    }

    // Probe active run for in-flight workflows. Completed runs skip this (404 is normal).
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
    clearLiveRunUi()
    const isCompleted = isTerminalHistoricalStatus(entry.status)
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
    setDraftConfig(null)
    setSelectedRun(null)
    navigate("/")
  }

  function handleResumeRun(res: RunResponse, workflowId: string) {
    setDraftConfig(null)
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
    try {
      const res = await resumeRun(entry)
      handleResumeRun(res, entry.workflow_id)
      toast.success("Resumed from last checkpoint")
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

  async function handleSidebarHideCompleted(workflowId: string) {
    await hideCompletedRun(workflowId)
    if (selectedRun?.workflowId === workflowId) {
      setSelectedRun(null)
      navigate("/", { replace: true })
    }
  }

  async function handleSidebarRestoreCompleted(workflowId: string) {
    await restoreCompletedRun(workflowId)
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

  function handleOpenSettings() {
    setSettingsOpen(true)
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
            onGenerateDraft={(req) => { void handleStartDraftConfig(req) }}
            onOpenDraftWithYaml={handleOpenDraftYaml}
            disabled={isRunning}
          />
        </Suspense>
      )
    }

    const isDraftRun = selectedRun.workflowId === "draft"
    const draftStatus = draftConfig?.isGenerating ? "streaming" : "awaiting_review"

    // Map the registry's raw status string to an SSE-style status for historical runs.
    const resolvedHistoricalStatus = isDraftRun
      ? draftStatus
      : (() => {
          const raw = selectedRun.historicalStatus ?? "completed"
          if (raw.toLowerCase() === "awaiting_review") return "awaiting_review"
          return resolveRunStatus(raw)
        })()
    const completedHistoricalRun =
      !isDraftRun &&
      !isViewingLiveRun &&
      ["completed", "done"].includes((selectedRun.historicalStatus ?? "").toLowerCase())
    const resumeModeActive = completedHistoricalRun

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
        historyOutputs={historyOutputs}
        liveOutputs={isViewingLiveRun ? liveOutputs : {}}
        dbUnlocked={Boolean(dbUnlocked)}
        isLive={isViewingLiveRun && isRunning && Boolean(dbUnlocked)}
        onResumeFromPhase={!isViewingLiveRun && !isDraftRun ? handleTimelineResumePhase : undefined}
        resumeModeActive={resumeModeActive}
        submissionFocusTarget={submissionFocusTarget}
        submissionFocusToken={submissionFocusToken}
        draftConfig={isDraftRun ? draftConfig : null}
        onRetryDraftGeneration={() => { void handleRetryDraftConfigGeneration() }}
        onLaunchDraft={(yaml) => { void handleLaunchDraftConfig(yaml) }}
      />
    )
  }

  const breadcrumbTopic = selectedRun?.topic ?? null

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
    <div className="flex h-dvh bg-background text-foreground overflow-hidden">
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
        onHideCompleted={handleSidebarHideCompleted}
        onRestoreCompleted={handleSidebarRestoreCompleted}
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
            background: "var(--app-ambient-gradient)",
          }}
        />
        {/* Backend offline banner */}
        {!isOnline && (
          <div className="flex flex-col items-start gap-1.5 bg-intent-warning-subtle border-b border-intent-warning-border px-6 py-2.5 text-xs text-intent-warning shrink-0">
            <span className="inline-flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span className="font-medium">Cannot reach backend API.</span>
            </span>
            <span className="text-intent-warning/70">
              If this run was detached after a restart, reopen it from History. Start backend with:{" "}
              <code className="font-mono bg-intent-warning-subtle px-1 py-0.5 rounded">
                pm2 start ecosystem.config.js
              </code>
            </span>
          </div>
        )}

        {/* Top bar -- paddingTop pushes content below the iOS status bar when viewport-fit=cover is active */}
        <header
          className="sticky top-0 z-30 glass-toolbar border-b border-border/70 shrink-0"
          style={{ paddingTop: 'env(safe-area-inset-top)' }}
        >
          <div className="h-14 flex items-center px-4 gap-3">
            {/* Hamburger: only visible on mobile to open the sidebar drawer */}
            {isMobile && (
              <button
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Open menu"
                className="flex items-center justify-center h-10 w-10 -ml-1 rounded-lg text-muted hover:text-foreground hover:bg-surface-2 transition-colors shrink-0"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            {/* Breadcrumb */}
            <TooltipProvider delayDuration={0}>
              <div className="flex items-center gap-1.5 text-sm flex-1 min-w-0">
                {breadcrumbTopic ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => void handleCopyTopic()}
                        className="text-muted font-medium truncate flex-1 min-w-0 text-left hover:text-foreground transition-colors cursor-pointer"
                      >
                        {breadcrumbTopic}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent
                      side="bottom"
                      className="max-w-md break-words bg-card border-border text-foreground"
                    >
                      {breadcrumbTopic}
                    </TooltipContent>
                  </Tooltip>
                ) : !selectedRun ? (
                  <span className="text-foreground font-medium">New Review</span>
                ) : null}
              </div>
            </TooltipProvider>
          </div>
        </header>

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
          onClick={handleOpenSettings}
          className="fixed bottom-4 right-4 z-40 inline-flex items-center justify-center h-10 w-10 rounded-full border border-border bg-card/95 text-muted shadow-lg hover:bg-surface-2 hover:text-foreground transition-colors"
          aria-label="Open settings"
          title="Settings"
        >
          <Settings className="h-4 w-4" />
        </button>
        <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      </main>
    </div>
  )
}
