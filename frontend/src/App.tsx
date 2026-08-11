import { useEffect, useState, Suspense, lazy, Component, useRef } from "react"
import type { ReactNode, ErrorInfo } from "react"
import { useNavigate } from "react-router-dom"
import { Toaster, toast } from "sonner"
import { AlertTriangle, Menu, Settings } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import { SettingsDialog } from "@/components/SettingsDialog"
import { RunSessionProvider } from "@/context/RunSessionProvider"
import { queryClient } from "@/lib/queryClient"
import { useRunSessionActions, useRunSessionState } from "@/hooks/useRunSession"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import {
  buildRunRequest,
  generateConfigStream,
  reserveWorkflowDraft,
  resolveStoredApiKeys,
  saveWorkflowConfigDraft,
} from "@/lib/api"
import { useDefaultReviewConfig } from "@/hooks/useRunConfig"
import { Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { isConfigDraftStatus, resolveRunStatus } from "@/lib/constants"
import { useRunChrome } from "@/hooks/useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { RunView } from "@/views/RunView"
import type { ConfigGenerateRequest } from "@/views/SetupView"
import type { ScreeningOverride } from "@/lib/api"

const SetupView = lazy(() => import("@/views/SetupView").then((m) => ({ default: m.SetupView })))

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

const EMPTY_SELECTED_RUN: SelectedRun = {
  runId: "",
  workflowId: null,
  topic: "",
  dbPath: null,
  isDone: false,
  startedAt: null,
}

export default function App() {
  return (
    <RunSessionProvider>
      <AppShell />
    </RunSessionProvider>
  )
}

function AppShell() {
  const navigate = useNavigate()
  const {
    selectedRun,
    activeRunTab,
    historyOutputs,
    submissionFocusTarget,
    submissionFocusToken,
    isRunning,
    isViewingLiveRun,
    viewEvents,
    liveOutputs,
    dbUnlocked,
    status,
    costStats,
  } = useRunSessionState()
  const {
    setSelectedRun,
    setActiveRunTab,
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
    handleTimelineResumePhase,
    handleTabChange,
    handleSubmitProsperoAndResume,
    handleApproveScreeningAndResume,
    openDraftRunShell,
  } = useRunSessionActions()

  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 639px)").matches)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  )
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const stored = localStorage.getItem("sidebar-width")
    return stored ? Math.max(200, Math.min(420, Number(stored))) : 240
  })
  const { data: defaultYaml = "" } = useDefaultReviewConfig()
  const [draftConfig, setDraftConfig] = useState<DraftConfigState | null>(null)
  const [prosperoPrepareInProgress, setProsperoPrepareInProgress] = useState(false)
  const [prosperoSubmitting, setProsperoSubmitting] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { isOnline } = useBackendHealth(6000, { suppressOffline: status === "streaming" })
  const prevOnlineRef = useRef(isOnline)

  const isDraftRun =
    selectedRun !== null &&
    (selectedRun.workflowId === "draft" ||
      draftConfig !== null ||
      isConfigDraftStatus(selectedRun.historicalStatus))
  const draftStatus =
    draftConfig?.isGenerating || selectedRun?.historicalStatus === "config_generating"
      ? "config_generating"
      : selectedRun?.historicalStatus === "config_ready"
        ? "config_ready"
        : "idle"
  const resolvedHistoricalStatus =
    selectedRun === null
      ? "idle"
      : isDraftRun
        ? draftStatus
        : resolveRunStatus(selectedRun.historicalStatus ?? "completed")

  const { liveStatus } = useRunChrome({
    run: selectedRun ?? EMPTY_SELECTED_RUN,
    events: viewEvents,
    effectiveEvents: viewEvents,
    isViewingLiveRun: selectedRun !== null && isViewingLiveRun,
    status: selectedRun !== null && isViewingLiveRun ? status : resolvedHistoricalStatus,
    streamStatus: status,
    costStats,
    liveOutputs,
    prosperoPrepareInProgress,
    resolvedHistoricalStatus,
  })

  useEffect(() => {
    if (selectedRun === null) {
      setDraftConfig(null)
      setProsperoPrepareInProgress(false)
    }
  }, [selectedRun])

  useEffect(() => {
    if (!prevOnlineRef.current && isOnline) {
      void queryClient.invalidateQueries()
    }
    prevOnlineRef.current = isOnline
  }, [isOnline])

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)")
    function handleChange(e: MediaQueryListEvent) {
      setIsMobile(e.matches)
      if (e.matches) setSidebarCollapsed(true)
    }
    mq.addEventListener("change", handleChange)
    return () => mq.removeEventListener("change", handleChange)
  }, [])

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

  async function handleStartDraftConfig(req: ConfigGenerateRequest) {
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
    let workflowId: string | null = null
    try {
      const reserved = await reserveWorkflowDraft(req.question)
      workflowId = reserved.workflow_id
      const now = new Date()
      setSelectedRun({
        runId: reserved.workflow_id,
        workflowId: reserved.workflow_id,
        topic: req.question,
        dbPath: reserved.db_path,
        isDone: false,
        historicalStatus: "config_generating",
        startedAt: now,
        createdAt: now.toISOString(),
      })
      setActiveRunTab("config")
      navigate(`/run/${reserved.workflow_id}/config`, { replace: true })
      void queryClient.invalidateQueries({ queryKey: ["history"] })

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
      await saveWorkflowConfigDraft(reserved.workflow_id, yaml)
      setDraftConfig((prev) => (prev ? { ...prev, yaml, isGenerating: false, generationError: null } : prev))
      setSelectedRun((prev) => (
        prev?.workflowId === reserved.workflow_id
          ? { ...prev, historicalStatus: "config_ready" }
          : prev
      ))
      void queryClient.invalidateQueries({ queryKey: ["history"] })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setDraftConfig((prev) => (prev ? { ...prev, isGenerating: false, generationError: message } : prev))
      if (workflowId) {
        setSelectedRun((prev) => (
          prev?.workflowId === workflowId
            ? { ...prev, historicalStatus: "config_generating" }
            : prev
        ))
      }
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

  async function handlePrepareProsperoConfig(yaml: string) {
    if (!draftConfig?.request) return
    const reservedWorkflowId =
      selectedRun?.workflowId && selectedRun.workflowId !== "draft"
        ? selectedRun.workflowId
        : undefined
    const req = buildRunRequest(
      yaml,
      resolveStoredApiKeys({ deepseek: draftConfig.request.deepseekKey }),
      undefined,
      reservedWorkflowId,
    )
    const prepareRequest = draftConfig.request
    setProsperoPrepareInProgress(true)
    try {
      if (prepareRequest.csvFile && prepareRequest.csvMode === "masterlist") {
        await handleStartWithMasterlistCsv(prepareRequest.csvFile, req, { tab: "config" })
      } else if (prepareRequest.csvFile) {
        await handleStartWithSupplementaryCsv(prepareRequest.csvFile, req, { tab: "config" })
      } else {
        await handleStart(req, { tab: "config" })
      }
      setDraftConfig((prev) => (prev ? { ...prev, yaml, isGenerating: false } : prev))
      setActiveRunTab("config")
    } catch (error) {
      setProsperoPrepareInProgress(false)
      const message = error instanceof Error ? error.message : String(error)
      toast.error(message || "Failed to generate PROSPERO draft")
    }
  }

  async function handleStartResearchAfterProspero(
    registration: { registration_number: string; registration_date: string },
  ) {
    const runId = selectedRun?.runId
    if (!runId || runId === "draft") return
    setProsperoSubmitting(true)
    try {
      await handleSubmitProsperoAndResume(runId, registration)
      setProsperoPrepareInProgress(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      toast.error(message || "Failed to start research")
    } finally {
      setProsperoSubmitting(false)
    }
  }

  async function handleApproveScreeningAndResumeWrapper(overrides: ScreeningOverride[]) {
    const runId = selectedRun?.runId
    if (!runId || runId === "draft") return
    await handleApproveScreeningAndResume(runId, overrides.length > 0 ? overrides : undefined)
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

  function handleSidebarWidthChange(w: number) {
    setSidebarWidth(w)
    localStorage.setItem("sidebar-width", String(w))
  }

  function handleOpenSettings() {
    setSettingsOpen(true)
  }

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

    const completedHistoricalRun =
      !isDraftRun &&
      !isViewingLiveRun &&
      ["completed", "done"].includes((selectedRun.historicalStatus ?? "").toLowerCase())
    const failedHistoricalRun =
      !isDraftRun &&
      !isViewingLiveRun &&
      ["failed", "error", "cancelled", "interrupted"].includes((selectedRun.historicalStatus ?? "").toLowerCase())
    const resumeModeActive = completedHistoricalRun || failedHistoricalRun

    return (
      <RunView
        run={selectedRun}
        events={viewEvents}
        isViewingLiveRun={isViewingLiveRun}
        status={liveStatus}
        costStats={isViewingLiveRun ? costStats : { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] }}
        activeTab={activeRunTab}
        onTabChange={handleTabChange}
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
        prosperoPrepareInProgress={prosperoPrepareInProgress}
        prosperoSubmitting={prosperoSubmitting}
        onPrepareProspero={(yaml) => { void handlePrepareProsperoConfig(yaml) }}
        onStartResearchAfterProspero={(registration) => {
          void handleStartResearchAfterProspero(registration)
        }}
        onApproveScreeningAndResume={handleApproveScreeningAndResumeWrapper}
      />
    )
  }

  const mainMargin = isMobile ? 0 : sidebarCollapsed ? 56 : sidebarWidth
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

        {/* Top bar -- research question for runs; "New Review" on setup */}
        <ViewToolbar
          sticky
          bordered
          className="shrink-0"
          style={{ paddingTop: "env(safe-area-inset-top)" }}
        >
          <div className="h-11 flex items-center gap-3 w-full min-w-0">
            {isMobile && (
              <button
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Open menu"
                className="flex items-center justify-center h-10 w-10 -ml-1 rounded-lg text-muted hover:text-foreground hover:bg-surface-2 transition-colors shrink-0"
              >
                <Menu className="h-5 w-5" />
              </button>
            )}
            <div className="flex flex-1 min-w-0 items-center">
              <TooltipProvider delayDuration={0}>
                {breadcrumbTopic ? (
                  <div className="flex items-center gap-3 w-full min-w-0">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted shrink-0">
                    Question
                  </span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => void handleCopyTopic()}
                        className="flex-1 min-w-0 text-sm text-foreground font-medium text-left truncate hover:text-foreground/90 transition-colors cursor-pointer"
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
                </div>
                ) : !selectedRun ? (
                  <span className="text-foreground font-medium">New Review</span>
                ) : null}
              </TooltipProvider>
            </div>
          </div>
        </ViewToolbar>

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
