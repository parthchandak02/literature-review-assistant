import { useEffect, useState, Suspense, lazy, Component, useRef } from "react"
import type { ReactNode, ErrorInfo } from "react"
import { Toaster, toast } from "sonner"
import { AlertTriangle, Menu, Settings } from "lucide-react"
import { Sidebar } from "@/components/Sidebar"
import { SettingsDialog } from "@/components/SettingsDialog"
import { RunSessionProvider } from "@/context/RunSessionProvider"
import { queryClient } from "@/lib/queryClient"
import { useRunSession } from "@/hooks/useRunSession"
import { useBackendHealth } from "@/hooks/useBackendHealth"
import {
  buildRunRequest,
  generateConfigStream,
  resolveStoredApiKeys,
} from "@/lib/api"
import { useDefaultReviewConfig } from "@/hooks/useRunConfig"
import { Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { resolveRunStatus } from "@/lib/constants"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { RunView } from "@/views/RunView"
import type { ConfigGenerateRequest } from "@/views/SetupView"

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

export default function App() {
  return (
    <RunSessionProvider>
      <AppShell />
    </RunSessionProvider>
  )
}

function AppShell() {
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
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
    handleTimelineResumePhase,
    handleTabChange,
    handleGoToSubmissionReferencePapers,
    openDraftRunShell,
  } = useRunSession()

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
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { isOnline } = useBackendHealth(6000, { suppressOffline: status === "streaming" })
  const prevOnlineRef = useRef(isOnline)

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
  const mainMargin = isMobile ? 0 : sidebarCollapsed ? 56 : sidebarWidth

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

        {/* Top bar -- paddingTop pushes content below the iOS status bar when viewport-fit=cover is active */}
        <ViewToolbar
          sticky
          bordered
          className="!h-auto shrink-0"
          style={{ paddingTop: 'env(safe-area-inset-top)' }}
        >
          <div className="h-14 flex items-center gap-3 w-full">
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
