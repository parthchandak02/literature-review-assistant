import { useEffect, useState, Suspense, lazy, Component, useRef } from "react"
import type { ReactNode, ErrorInfo } from "react"
import { useNavigate } from "react-router-dom"
import { Toaster, toast } from "sonner"
import { AlertTriangle, Copy, Home, Menu, RotateCw } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import { MOBILE_MENU_BUTTON_ID } from "@/components/sidebar/sidebarLayout"
import { SettingsProvider, useSettings } from "@/context/SettingsContext"
import { RunSessionProvider } from "@/context/RunSessionProvider"
import { queryClient } from "@/lib/queryClient"
import { useRunSessionActions, useRunSessionState } from "@/hooks/useRunSession"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import { useDefaultReviewConfig } from "@/hooks/useRunConfig"
import {
  deriveDraftStatus,
  deriveIsDraftRun,
  deriveResolvedHistoricalStatus,
  useDraftConfigFlow,
} from "@/hooks/useDraftConfigFlow"
import { Spinner } from "@/components/ui/feedback"
import { Button } from "@/components/ui/button"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { useRunChrome } from "@/hooks/useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { RunView } from "@/views/RunView"
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
        <div
          role="alert"
          className="flex flex-col items-center justify-center h-screen bg-background text-foreground gap-4 p-8 text-center"
        >
          <AlertTriangle className="h-10 w-10 text-intent-danger" aria-hidden />
          <h1 className="text-xl font-semibold text-foreground">Something went wrong</h1>
          <p className="text-muted text-sm max-w-md">
            The page hit an unexpected error. Reloading usually fixes it.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button type="button" onClick={() => window.location.reload()}>
              <RotateCw className="h-4 w-4" aria-hidden />
              Reload this page
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                this.setState({ hasError: false, message: "" })
                window.location.assign("/")
              }}
            >
              <Home className="h-4 w-4" aria-hidden />
              Go home
            </Button>
          </div>
          <details className="max-w-md text-left text-xs text-muted">
            <summary className="cursor-pointer select-none rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Technical details
            </summary>
            <pre className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] font-mono text-xs">
              {this.state.message}
            </pre>
          </details>
        </div>
      )
    }
    return this.props.children
  }
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
      <SettingsProvider>
        <AppShell />
      </SettingsProvider>
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
    handleUpdateProsperoRegistration,
    handleRegenerateProsperoDocs,
    handleApproveScreeningAndResume,
    handleSelectLiveRun,
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
  const {
    draftConfig,
    prosperoPrepareInProgress,
    prosperoSubmitting,
    setProsperoPrepareInProgress,
    setProsperoSubmitting,
    handleStartDraftConfig,
    handleOpenDraftYaml,
    handleRetryDraftGeneration,
    handlePrepareProsperoConfig,
    handleLaunchDraftConfig,
  } = useDraftConfigFlow({
    selectedRun,
    navigate,
    setSelectedRun,
    setActiveRunTab,
    openDraftRunShell,
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
  })
  const [prosperoRegenerating, setProsperoRegenerating] = useState(false)
  const { openSettings } = useSettings()
  const { isOnline, checking: checkingBackend, retry: retryBackend } = useBackendHealth(6000, { suppressOffline: status === "streaming" })
  const prevOnlineRef = useRef(isOnline)

  const isDraftRun = deriveIsDraftRun(selectedRun, draftConfig)
  const draftStatus = deriveDraftStatus(draftConfig, selectedRun?.historicalStatus)
  const resolvedHistoricalStatus = deriveResolvedHistoricalStatus(
    selectedRun,
    isDraftRun,
    draftStatus,
  )

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
      const target = e.target
      const editable =
        target instanceof HTMLElement &&
        (target.isContentEditable || target.closest("input, textarea, select") !== null)
      if (editable) return
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault()
        setSidebarCollapsed((v) => !v)
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

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

  async function handleSaveProsperoRegistration(
    registration: { registration_number: string; registration_date: string },
  ) {
    const runId = selectedRun?.runId
    if (!runId || runId === "draft") return
    setProsperoSubmitting(true)
    try {
      await handleUpdateProsperoRegistration(runId, registration)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      toast.error(message || "Failed to save PROSPERO registration")
    } finally {
      setProsperoSubmitting(false)
    }
  }

  async function handleRegenerateProsperoDrafts() {
    const runId = selectedRun?.runId
    if (!runId || runId === "draft") return
    setProsperoRegenerating(true)
    try {
      await handleRegenerateProsperoDocs(runId)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      toast.error(message || "Failed to regenerate PROSPERO drafts")
    } finally {
      setProsperoRegenerating(false)
    }
  }

  async function handleApproveScreeningAndResumeWrapper(overrides: ScreeningOverride[]) {
    const runId = selectedRun?.runId
    if (!runId || runId === "draft") return
    await handleApproveScreeningAndResume(runId, overrides.length > 0 ? overrides : undefined)
  }

  function handleSidebarWidthChange(w: number) {
    setSidebarWidth(w)
    localStorage.setItem("sidebar-width", String(w))
  }

  function handleOpenSettings() {
    openSettings()
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
            onOpenLiveRun={handleSelectLiveRun}
          />
        </Suspense>
      )
    }

    const completedHistoricalRun =
      !isDraftRun &&
      !isViewingLiveRun &&
      ["completed", "done", "needs_revision"].includes((selectedRun.historicalStatus ?? "").toLowerCase())
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
        isSSEConnected={isViewingLiveRun && liveStatus === "streaming"}
        onResumeFromPhase={!isViewingLiveRun && !isDraftRun ? handleTimelineResumePhase : undefined}
        resumeModeActive={resumeModeActive}
        submissionFocusTarget={submissionFocusTarget}
        submissionFocusToken={submissionFocusToken}
        draftConfig={isDraftRun ? draftConfig : null}
        onRetryDraftGeneration={() => { void handleRetryDraftGeneration() }}
        onLaunchDraft={(yaml) => { void handleLaunchDraftConfig(yaml) }}
        prosperoPrepareInProgress={prosperoPrepareInProgress}
        prosperoSubmitting={prosperoSubmitting}
        prosperoRegenerating={prosperoRegenerating}
        onPrepareProspero={(yaml) => { void handlePrepareProsperoConfig(yaml) }}
        onStartResearchAfterProspero={(registration) => {
          void handleStartResearchAfterProspero(registration)
        }}
        onSaveProsperoRegistration={(registration) => {
          void handleSaveProsperoRegistration(registration)
        }}
        onRegenerateProsperoDrafts={() => {
          void handleRegenerateProsperoDrafts()
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
      toast.success("Question copied")
    } catch {
      toast.error("Failed to copy")
    }
  }

  return (
    <div className="flex h-dvh bg-background text-foreground overflow-hidden">
      <Toaster position="bottom-right" richColors closeButton />
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        width={sidebarWidth}
        onWidthChange={handleSidebarWidthChange}
        isMobile={isMobile}
        onOpenSettings={handleOpenSettings}
      />

      <main
        className="relative isolate flex-1 h-full overflow-hidden overscroll-none flex flex-col transition-[margin-left] duration-200 ease-in-out"
        style={{ marginLeft: mainMargin }}
      >
        {!isOnline && (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-x-3 gap-y-1.5 bg-intent-warning-subtle border-b border-intent-warning-border px-6 py-2.5 text-xs text-intent-warning shrink-0"
          >
            <span className="inline-flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="font-medium">Can&apos;t reach the server. Retrying…</span>
            </span>
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => void retryBackend()}
              disabled={checkingBackend}
            >
              {checkingBackend ? "Checking…" : "Retry now"}
            </Button>
            <span className="text-intent-warning-text">
              This page reconnects on its own. If a review stopped, reopen it from the sidebar once the server is back.
            </span>
            {import.meta.env.DEV && (
              <details className="text-intent-warning-text">
                <summary className="cursor-pointer select-none rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  Technical details
                </summary>
                <p className="mt-1">
                  Requests to <code className="font-mono">/api/health</code> are failing. Check that the API
                  process is running (<code className="font-mono">pm2 status</code>).
                </p>
              </details>
            )}
          </div>
        )}

        {/* Top bar -- research question for runs; empty on setup, where the page h1 names it */}
        <ViewToolbar
          sticky
          bordered
          className="shrink-0"
          style={{ paddingTop: "env(safe-area-inset-top)" }}
        >
          <div className="h-11 flex items-center gap-3 w-full min-w-0">
            {isMobile && (
              <button
                id={MOBILE_MENU_BUTTON_ID}
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Open menu"
                aria-expanded={!sidebarCollapsed}
                aria-haspopup="dialog"
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
                      <p className="flex-1 min-w-0 text-sm text-foreground font-medium truncate">
                        {breadcrumbTopic}
                      </p>
                    </TooltipTrigger>
                    <TooltipContent
                      side="bottom"
                      className="max-w-md break-words bg-card border-border text-foreground"
                    >
                      {breadcrumbTopic}
                    </TooltipContent>
                  </Tooltip>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => void handleCopyTopic()}
                    aria-label="Copy question"
                    title="Copy question"
                    className="shrink-0 text-muted hover:text-foreground"
                  >
                    <Copy aria-hidden />
                  </Button>
                </div>
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
      </main>
    </div>
  )
}
