import { useMemo, useState } from "react"
import { AlertTriangle, FileCode } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { useRunConfig } from "@/hooks/useRunConfig"
import { EmptyState } from "@/components/ui/feedback"
import { Button } from "@/components/ui/button"
import { YamlEditor } from "@/components/YamlEditor"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { ProsperoGatePanel } from "@/components/config/ProsperoGatePanel"
import { ConfigGenerationStepper, type ConfigGenStepDisplay, type ConfigGenStepStatus } from "@/components/config/ConfigGenerationStepper"
import { GEN_STEPS } from "@/components/setup/constants"
import { buildGenerationStepDetail } from "@/components/setup/generationHelpers"
import type { ProsperoRegistration } from "@/lib/api"
import { isProsperoRegistrationComplete, parseProsperoFromYaml } from "@/lib/prosperoConfig"

// ---------------------------------------------------------------------------
// ConfigView
// ---------------------------------------------------------------------------

export interface ConfigViewProps {
  /** Workflow ID for fetching the persisted review config. */
  workflowId: string | null
  draftConfig?: DraftConfigContext | null
  onRetryDraftGeneration?: () => void
  onLaunchDraft?: (yaml: string) => void
  runId?: string | null
  isAwaitingProspero?: boolean
  prosperoPrepareInProgress?: boolean
  prosperoSubmitting?: boolean
  prosperoRegenerating?: boolean
  onPrepareProspero?: (yaml: string) => void
  onStartResearchAfterProspero?: (registration: ProsperoRegistration) => void | Promise<void>
  onSaveProsperoRegistration?: (registration: ProsperoRegistration) => void | Promise<void>
  onRegenerateProsperoDrafts?: () => void | Promise<void>
}

export interface DraftConfigContext {
  request: { question: string } | null
  yaml: string
  isGenerating: boolean
  activeStep: string
  stepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
  generationError: string | null
}

type StepStatus = ConfigGenStepStatus
type GenerationMode = "web_grounded" | "model_fallback"

interface ConfigGenerationSummary {
  mode: GenerationMode
  fallbackReason: string | null
}

function getFallbackStepLabel(status: StepStatus): string {
  if (status === "skipped") return "Web research backup skipped"
  if (status === "degraded") return "Web search unavailable"
  return "Web research backup (standby)"
}

export function ConfigView({
  workflowId,
  draftConfig = null,
  onRetryDraftGeneration,
  runId = null,
  isAwaitingProspero = false,
  prosperoPrepareInProgress = false,
  prosperoSubmitting = false,
  prosperoRegenerating = false,
  onPrepareProspero,
  onStartResearchAfterProspero,
  onSaveProsperoRegistration,
  onRegenerateProsperoDrafts,
}: ConfigViewProps) {
  const isDraft = draftConfig !== null
  const streamedDraftYaml = draftConfig?.yaml ?? ""
  const [draftYamlOverride, setDraftYamlOverride] = useState<string | null>(null)
  const draftYaml = draftYamlOverride ?? streamedDraftYaml
  const {
    data: yamlContent = null,
    isLoading: loading,
    error: queryError,
  } = useRunConfig(workflowId, { enabled: !isDraft && Boolean(workflowId) })
  const error = queryError
    ? (queryError instanceof Error ? queryError.message : "Failed to load config")
    : !loading && yamlContent === null && workflowId && !isDraft
      ? "Config not saved for this run. Older CLI runs may not have review.yaml persisted."
      : null

  const generationSummary = useMemo<ConfigGenerationSummary | null>(() => {
    if (isDraft && draftConfig) {
      return { mode: draftConfig.usedWebFallback ? "model_fallback" : "web_grounded", fallbackReason: draftConfig.fallbackReason }
    }
    if (!yamlContent) return null
    // Legacy runs may not include generation header comments yet; keep the
    // summary panel visible with a safe default so layout remains consistent.
    return parseConfigGenerationSummary(yamlContent) ?? { mode: "web_grounded", fallbackReason: null }
  }, [draftConfig, isDraft, yamlContent])

  const draftActiveStepIndex = useMemo(() => {
    if (!draftConfig) return -1
    return GEN_STEPS.findIndex((step) => step.key === draftConfig.activeStep)
  }, [draftConfig])

  const generationSteps = useMemo<ConfigGenStepDisplay[] | null>(() => {
    if (!generationSummary) return null
    return GEN_STEPS.map((step) => {
      const status = isDraft && draftConfig
        ? getDraftGenerationStepStatus(step.key, draftConfig, draftActiveStepIndex)
        : getGenerationStepStatus(step.key, generationSummary.mode)
      const label =
        step.key === "web_research_fallback"
          ? getFallbackStepLabel(status)
          : step.label
      const detail = buildGenerationStepDetail(
        step.key,
        status,
        isDraft && draftConfig && status === "active" ? draftConfig.stepMetadata : {},
        step.detail,
        {
          fallbackReason: generationSummary.fallbackReason,
        },
      )
      return {
        key: step.key,
        label,
        shortLabel: step.shortLabel,
        detail,
        status,
      }
    })
  }, [draftActiveStepIndex, draftConfig, generationSummary, isDraft])

  const showProsperoGate = isAwaitingProspero || prosperoPrepareInProgress
  const showDraftPrepareButton = isDraft && !showProsperoGate
  const savedDraftYaml = draftConfig?.yaml ?? ""
  const effectiveYaml = isDraft ? draftYaml : (yamlContent ?? savedDraftYaml)
  const parsedProspero = useMemo(
    () => parseProsperoFromYaml(effectiveYaml),
    [effectiveYaml],
  )
  const registrationComplete = isProsperoRegistrationComplete(parsedProspero)
  const showRegistrationPanel = Boolean(effectiveYaml.trim()) && (showProsperoGate || !isDraft)
  const registrationInitial = parsedProspero.registrationNumber || parsedProspero.registrationDate
    ? {
        registration_number: parsedProspero.registrationNumber,
        registration_date: parsedProspero.registrationDate,
      }
    : null

  if (loading && !isDraft) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-muted">
        <Spinner size="xl" />
        <p className="text-sm">Loading config...</p>
      </div>
    )
  }

  if (!workflowId && !isDraft) {
    return (
      <EmptyState
        icon={FileCode}
        heading="Config pending"
        sub="Workflow ID is not assigned yet. Config will be available shortly."
        className="py-12"
      />
    )
  }

  if (error && !yamlContent && !isDraft) {
    return (
      <EmptyState
        icon={FileCode}
        heading="Config not available"
        sub={error}
        className="py-12"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {(yamlContent || isDraft) && (
        <>
          {generationSteps && (
            <ConfigGenerationStepper steps={generationSteps} />
          )}

          {showRegistrationPanel ? (
            <ProsperoGatePanel
              runId={runId}
              workflowId={workflowId}
              mode={showProsperoGate ? "gate" : "manage"}
              initialRegistration={registrationInitial}
              isComplete={registrationComplete}
              attention={isAwaitingProspero}
              disabled={prosperoPrepareInProgress && !isAwaitingProspero}
              isSubmitting={prosperoSubmitting}
              isRegenerating={prosperoRegenerating}
              onStartResearch={onStartResearchAfterProspero}
              onSaveRegistration={onSaveProsperoRegistration}
              onRegenerateDrafts={onRegenerateProsperoDrafts}
            />
          ) : null}

          <div className="card-surface overflow-hidden">
            <ViewToolbar
              className="!h-auto py-3"
              title={<h3 className="text-sm font-semibold text-foreground">Review Config (YAML)</h3>}
              actions={
                <span className="text-xs text-muted">
                  {isDraft ? "Generated live before launch" : "Timestamped config used for this run"}
                </span>
              }
            />
            <div className="px-4 py-4 space-y-3">
              {isDraft && draftConfig?.generationError && (
                <div className="rounded-md border border-intent-warning-border bg-intent-warning-subtle p-3 text-xs text-intent-warning">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-intent-warning" />
                    <div className="space-y-2">
                      <p>Config generation failed: {draftConfig.generationError}</p>
                      {onRetryDraftGeneration && (
                        <Button size="sm" variant="outline" onClick={onRetryDraftGeneration}>
                          Retry generation
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )}
              {isDraft ? (
                <>
                  <YamlEditor
                    value={draftYaml}
                    onChange={setDraftYamlOverride}
                    isLoading={draftConfig?.isGenerating}
                    loadingLabel="Generating review config from your research question..."
                  />
                  <div className="flex items-center justify-end gap-2">
                    {draftConfig?.request === null && (
                      <span className="text-xs text-muted mr-auto">
                        Launch is disabled for pasted/legacy configs started from setup.
                      </span>
                    )}
                    {showDraftPrepareButton ? (
                      <Button
                        onClick={() => onPrepareProspero?.(draftYaml)}
                        disabled={
                          !onPrepareProspero ||
                          draftConfig?.request === null ||
                          draftConfig?.isGenerating ||
                          prosperoPrepareInProgress ||
                          !draftYaml.trim()
                        }
                      >
                        {prosperoPrepareInProgress ? (
                          <>
                            <Spinner size="sm" className="mr-2" />
                            Generating PROSPERO draft...
                          </>
                        ) : (
                          "Generate PROSPERO Draft"
                        )}
                      </Button>
                    ) : null}
                  </div>
                </>
              ) : (
                <>
                  <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-[70vh] overflow-y-auto leading-relaxed">
                    {effectiveYaml}
                  </pre>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function parseConfigGenerationSummary(yaml: string): ConfigGenerationSummary | null {
  const modeMatch = yaml.match(/# Config generation mode:\s*(.+)/)
  if (!modeMatch) return null
  const modeText = modeMatch[1].trim().toLowerCase()
  const mode: GenerationMode = modeText.includes("fallback") ? "model_fallback" : "web_grounded"
  const reasonMatch = yaml.match(/# Web research fallback reason:\s*(.+)/)
  return {
    mode,
    fallbackReason: reasonMatch ? reasonMatch[1].trim() : null,
  }
}

function getGenerationStepStatus(stepKey: string, mode: GenerationMode): StepStatus {
  if (stepKey === "web_research_fallback") {
    return mode === "model_fallback" ? "degraded" : "skipped"
  }
  return "done"
}

function getDraftGenerationStepStatus(
  stepKey: string,
  draft: DraftConfigContext,
  activeStepIndex: number,
): StepStatus {
  const idx = GEN_STEPS.findIndex((step) => step.key === stepKey)
  const normalizedActive = activeStepIndex >= 0 ? activeStepIndex : 0

  if (stepKey === "web_research_fallback") {
    if (draft.usedWebFallback) return "degraded"
    if (normalizedActive > idx || !draft.isGenerating) return "skipped"
    return "pending"
  }

  if (idx < normalizedActive) return "done"
  if (idx === normalizedActive) return draft.isGenerating ? "active" : "done"
  if (!draft.isGenerating && draft.yaml.trim().length > 0) return "done"
  return "pending"
}
