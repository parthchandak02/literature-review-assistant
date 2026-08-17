import { useState } from "react"
import type { NavigateFunction } from "react-router-dom"
import { toast } from "sonner"
import { queryClient } from "@/lib/queryClient"
import {
  buildRunRequest,
  generateConfigStream,
  reserveWorkflowDraft,
  resolveStoredApiKeys,
  saveWorkflowConfigDraft,
} from "@/lib/api"
import { isConfigDraftStatus, resolveRunStatus } from "@/lib/constants"
import type { SelectedRun, RunTab } from "@/context/runSessionTypes"
import type { ConfigGenerateRequest } from "@/components/setup/types"
import type { RunRequest } from "@/lib/api/types"

export interface DraftConfigState {
  request: ConfigGenerateRequest | null
  yaml: string
  isGenerating: boolean
  activeStep: string
  stepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
  generationError: string | null
}

export function deriveIsDraftRun(
  selectedRun: SelectedRun | null,
  draftConfig: DraftConfigState | null,
): boolean {
  return (
    selectedRun !== null &&
    (selectedRun.workflowId === "draft" ||
      draftConfig !== null ||
      isConfigDraftStatus(selectedRun.historicalStatus))
  )
}

export function deriveDraftStatus(
  draftConfig: DraftConfigState | null,
  historicalStatus: string | null | undefined,
): "config_generating" | "config_ready" | "idle" {
  if (draftConfig?.isGenerating || historicalStatus === "config_generating") {
    return "config_generating"
  }
  if (historicalStatus === "config_ready") {
    return "config_ready"
  }
  return "idle"
}

export function deriveResolvedHistoricalStatus(
  selectedRun: SelectedRun | null,
  isDraftRun: boolean,
  draftStatus: "config_generating" | "config_ready" | "idle",
): string {
  if (selectedRun === null) return "idle"
  if (isDraftRun) return draftStatus
  return resolveRunStatus(selectedRun.historicalStatus ?? "completed")
}

interface RunStartOptions {
  tab?: RunTab
}

interface UseDraftConfigFlowDeps {
  selectedRun: SelectedRun | null
  navigate: NavigateFunction
  setSelectedRun: (run: SelectedRun | null | ((prev: SelectedRun | null) => SelectedRun | null)) => void
  setActiveRunTab: (tab: RunTab) => void
  openDraftRunShell: (topic: string) => void
  handleStart: (req: RunRequest, options?: RunStartOptions) => Promise<void>
  handleStartWithSupplementaryCsv: (
    file: File,
    req: RunRequest,
    options?: RunStartOptions,
  ) => Promise<void>
  handleStartWithMasterlistCsv: (
    file: File,
    req: RunRequest,
    options?: RunStartOptions,
  ) => Promise<void>
}

export function useDraftConfigFlow(deps: UseDraftConfigFlowDeps) {
  const {
    selectedRun,
    navigate,
    setSelectedRun,
    setActiveRunTab,
    openDraftRunShell,
    handleStart,
    handleStartWithSupplementaryCsv,
    handleStartWithMasterlistCsv,
  } = deps

  const [draftConfig, setDraftConfig] = useState<DraftConfigState | null>(null)
  const [prosperoPrepareInProgress, setProsperoPrepareInProgress] = useState(false)
  const [prosperoSubmitting, setProsperoSubmitting] = useState(false)

  const visibleDraftConfig = selectedRun === null ? null : draftConfig
  const visibleProsperoPrepareInProgress =
    selectedRun === null ? false : prosperoPrepareInProgress
  const visibleProsperoSubmitting = selectedRun === null ? false : prosperoSubmitting

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
        req.fireworksKey,
        req.generationProfile,
        (step, metadata) => {
          const normalizedStep = step === "structuring_retry" ? "structuring" : step
          setDraftConfig((prev) => {
            if (!prev) return prev
            const reason =
              step === "web_research_fallback" && typeof metadata?.reason === "string"
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
      setDraftConfig((prev) =>
        prev ? { ...prev, yaml, isGenerating: false, generationError: null } : prev,
      )
      setSelectedRun((prev) =>
        prev?.workflowId === reserved.workflow_id
          ? { ...prev, historicalStatus: "config_ready" }
          : prev,
      )
      void queryClient.invalidateQueries({ queryKey: ["history"] })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setDraftConfig((prev) => (prev ? { ...prev, isGenerating: false, generationError: message } : prev))
      if (workflowId) {
        setSelectedRun((prev) =>
          prev?.workflowId === workflowId ? { ...prev, historicalStatus: "config_generating" } : prev,
        )
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

  async function handleRetryDraftGeneration() {
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
      resolveStoredApiKeys({ fireworks: draftConfig.request.fireworksKey }),
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

  async function handleLaunchDraftConfig(yaml: string) {
    if (!draftConfig?.request) return
    const req = buildRunRequest(
      yaml,
      resolveStoredApiKeys({ fireworks: draftConfig.request.fireworksKey }),
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

  return {
    draftConfig: visibleDraftConfig,
    prosperoPrepareInProgress: visibleProsperoPrepareInProgress,
    prosperoSubmitting: visibleProsperoSubmitting,
    setProsperoPrepareInProgress,
    setProsperoSubmitting,
    handleStartDraftConfig,
    handleOpenDraftYaml,
    handleRetryDraftGeneration,
    handlePrepareProsperoConfig,
    handleLaunchDraftConfig,
  }
}
