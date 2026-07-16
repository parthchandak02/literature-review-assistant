import { useMemo, useState } from "react"
import { AlertTriangle, Clock, FileCode, Sparkles } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { useRunConfig } from "@/hooks/useRunConfig"
import { formatRunDate } from "@/lib/format"
import { EmptyState } from "@/components/ui/feedback"
import { Button } from "@/components/ui/button"
import { YamlEditor } from "@/components/YamlEditor"
import { ViewToolbar } from "@/components/ui/view-toolbar"

// ---------------------------------------------------------------------------
// ConfigView
// ---------------------------------------------------------------------------

export interface ConfigViewProps {
  /** Workflow ID for fetching the persisted review config. */
  workflowId: string | null
  /** Fallback topic/research question when YAML is not yet available. */
  topic: string
  /** Run completion timestamp for display. */
  createdAt?: string | null
  draftConfig?: DraftConfigContext | null
  onRetryDraftGeneration?: () => void
  onLaunchDraft?: (yaml: string) => void
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

type StepStatus = "done" | "degraded" | "skipped" | "active" | "pending"
type GenerationMode = "web_grounded" | "model_fallback"

interface ConfigGenerationSummary {
  mode: GenerationMode
  fallbackReason: string | null
}

const CONFIG_GEN_STEPS: { key: string; label: string; detail: string }[] = [
  { key: "start", label: "Analyzing your research question", detail: "Understanding scope, domain, and intent" },
  { key: "web_research", label: "Searching the web", detail: "Discovering brand names, synonyms, and domain terminology" },
  {
    key: "web_research_fallback",
    label: "Web search unavailable",
    detail: "Falling back to model knowledge for this generation",
  },
  { key: "web_research_done", label: "Processing search results", detail: "Building research brief from web findings" },
  { key: "structuring", label: "Generating PICO and criteria", detail: "Keywords, inclusion/exclusion criteria, domain and scope" },
  { key: "topic_routing", label: "Applying domain routing policy", detail: "Selecting connector policy from confidence-scored topic signals" },
  { key: "finalizing", label: "Finalizing your config", detail: "Validating and serializing to YAML" },
]

function getFallbackStepLabel(status: StepStatus): string {
  if (status === "skipped") return "Web research backup skipped"
  if (status === "degraded") return "Web search unavailable"
  return "Web research backup (standby)"
}

export function ConfigView({
  workflowId,
  topic,
  createdAt,
  draftConfig = null,
  onRetryDraftGeneration,
  onLaunchDraft,
}: ConfigViewProps) {
  const isDraft = workflowId === "draft" && draftConfig !== null
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

  const researchQuestion = isDraft
    ? draftConfig?.request?.question ?? topic
    :
    yamlContent != null
      ? (() => {
          try {
            const parsed = parseYamlResearchQuestion(yamlContent)
            return parsed ?? topic
          } catch {
            return topic
          }
        })()
      : topic
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
    return CONFIG_GEN_STEPS.findIndex((step) => step.key === draftConfig.activeStep)
  }, [draftConfig])

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
    <div className="flex flex-col gap-4">
      <div className="card-surface overflow-hidden">
        <ViewToolbar
          className="!h-auto py-3"
          title={<h3 className="text-sm font-semibold text-foreground">Research Question</h3>}
        />
        <div className="px-4 py-4">
          <p className="text-sm text-foreground leading-relaxed">{researchQuestion}</p>
          {createdAt && (
            <div className="mt-2 inline-flex items-center gap-1.5 glass-chip text-foreground">
              <Clock className="h-3.5 w-3.5 text-muted" />
              <span className="text-xs">Run completed {formatRunDate(createdAt)}</span>
            </div>
          )}
        </div>
      </div>

      {(yamlContent || isDraft) && (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(320px,430px)_minmax(0,1fr)] gap-4 items-start">
          <div className="card-surface overflow-hidden">
            <ViewToolbar
              className="!h-auto py-3"
              title={
                <>
                  <Sparkles className="h-3.5 w-3.5 text-muted shrink-0" />
                  <h3 className="text-sm font-semibold text-foreground">Config Generation Summary</h3>
                </>
              }
            />
            <div className="px-3 py-3 space-y-1.5">
              {generationSummary && CONFIG_GEN_STEPS.map((step) => {
                const status = isDraft && draftConfig
                  ? getDraftGenerationStepStatus(step.key, draftConfig, draftActiveStepIndex)
                  : getGenerationStepStatus(step.key, generationSummary.mode)
                const style = getStatusStyle(status)
                const label =
                  step.key === "web_research_fallback"
                    ? getFallbackStepLabel(status)
                    : step.label
                const detail =
                  step.key === "web_research_fallback" && status === "degraded" && generationSummary.fallbackReason
                    ? `Falling back to model knowledge: ${generationSummary.fallbackReason}`
                    : status === "skipped"
                    ? "Skipped because web research succeeded."
                    : status === "active"
                    ? "In progress..."
                    : step.detail
                return (
                  <div key={step.key} className={`rounded-lg border px-2.5 py-2 ${style.row}`}>
                    <div className="flex items-center gap-2">
                      {status === "active" ? (
                        <Spinner size="sm" />
                      ) : (
                        <span className={`h-2 w-2 rounded-full border ${style.dot}`} />
                      )}
                      <p className={`text-xs font-medium ${style.text}`}>{label}</p>
                    </div>
                    <p className="text-[11px] text-muted mt-1 leading-snug">{detail}</p>
                  </div>
                )
              })}
            </div>
          </div>

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
                    <Button
                      onClick={() => onLaunchDraft?.(draftYaml)}
                      disabled={
                        !onLaunchDraft ||
                        draftConfig?.request === null ||
                        draftConfig?.isGenerating ||
                        !draftYaml.trim()
                      }
                    >
                      Launch Review
                    </Button>
                  </div>
                </>
              ) : (
                <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words max-h-[70vh] overflow-y-auto leading-relaxed">
                  {yamlContent}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function parseYamlResearchQuestion(yaml: string): string | null {
  const match = yaml.match(/research_question:\s*["']?([^"'\n]+)["']?/)
  return match ? match[1].trim() : null
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

function getStatusStyle(status: StepStatus): { row: string; dot: string; text: string } {
  if (status === "active") {
    return {
      row: "bg-intent-active-subtle border-intent-active-border",
      dot: "bg-intent-active border-intent-active-border",
      text: "text-intent-active",
    }
  }
  if (status === "pending") {
    return {
      row: "bg-card/60 border-border/70",
      dot: "bg-surface-3 border-surface-4/80",
      text: "text-muted",
    }
  }
  if (status === "degraded") {
    return {
      row: "bg-intent-warning-subtle border-intent-warning-border",
      dot: "bg-intent-warning border-intent-warning-border",
      text: "text-intent-warning",
    }
  }
  if (status === "skipped") {
    return {
      row: "bg-intent-info-subtle border-intent-info-border",
      dot: "bg-intent-info border-intent-info-border",
      text: "text-intent-info",
    }
  }
  return {
      row: "bg-intent-success-subtle border-intent-success-border",
      dot: "bg-intent-success border-intent-success-border",
      text: "text-intent-success",
  }
}

function getDraftGenerationStepStatus(
  stepKey: string,
  draft: DraftConfigContext,
  activeStepIndex: number,
): StepStatus {
  const idx = CONFIG_GEN_STEPS.findIndex((step) => step.key === stepKey)
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
