import { useEffect, useState } from "react"
import { ChevronLeft, FileCode2, Key, Sparkles, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner, FetchError } from "@/components/ui/feedback"
import { PageSection } from "@/components/ui/section"
import { YamlEditor } from "@/components/YamlEditor"
import {
  buildRunRequest,
  emptyStoredApiKeys,
  fetchEnvKeys,
  fetchRequiredLlmUiKeys,
  loadApiKeys,
  saveApiKeys,
} from "@/lib/api"
import type { RunRequest, StoredApiKeys } from "@/lib/api"
import type { CsvMode } from "./types"
import { GenerationProgressCard } from "./GenerationProgressCard"
import { SetupApiKeysSection } from "./SetupApiKeysSection"

interface ConfigReviewStageProps {
  yaml: string
  onYamlChange: (y: string) => void
  question: string | null
  onBack: () => void
  onSubmit: (req: RunRequest) => Promise<void>
  onSubmitWithSupplementaryCsv?: (csvFile: File, req: RunRequest) => Promise<void>
  onSubmitWithMasterlistCsv?: (csvFile: File, req: RunRequest) => Promise<void>
  csvFile?: File | null
  csvMode?: CsvMode
  disabled: boolean
  defaultYaml: string
  isGeneratingConfig: boolean
  activeGenStep: string
  activeStepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
  generationError: string | null
  onRetryGeneration: () => void
  showGenerationSummary: boolean
}

export function ConfigReviewStage({
  yaml,
  onYamlChange,
  question,
  onBack,
  onSubmit,
  onSubmitWithSupplementaryCsv,
  onSubmitWithMasterlistCsv,
  csvFile,
  csvMode = "supplementary",
  disabled,
  defaultYaml,
  isGeneratingConfig,
  activeGenStep,
  activeStepMetadata,
  usedWebFallback,
  fallbackReason,
  generationError,
  onRetryGeneration,
  showGenerationSummary,
}: ConfigReviewStageProps) {
  const [keys, setKeys] = useState<StoredApiKeys>(() => {
    const saved = loadApiKeys()
    // Merge saved keys with defaults so that newly-added fields get empty-string
    // values even when the persisted object predates them (avoids undefined ->
    // uncontrolled input problem in React).
    return saved ? { ...emptyStoredApiKeys(), ...saved } : emptyStoredApiKeys()
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [requiredLlmUiKeys, setRequiredLlmUiKeys] = useState<string[]>(["deepseek"])

  // On mount, backfill any empty fields with values from the server's .env.
  // localStorage always wins; env fills in blanks the user hasn't set yet.
  // Use .trim() so whitespace-only or "undefined" string values count as blank.
  useEffect(() => {
    fetchEnvKeys().then((envKeys) => {
      setKeys((prev) => {
        const merged = { ...prev }
        for (const k of Object.keys(envKeys) as (keyof typeof envKeys)[]) {
          const current = String(merged[k] ?? "").trim()
          if ((!current || current === "undefined") && envKeys[k]) {
            merged[k] = envKeys[k]
          }
        }
        return merged
      })
    })
    fetchRequiredLlmUiKeys().then((keys) => {
      if (keys.length > 0) {
        setRequiredLlmUiKeys(keys)
      }
    })
  }, [])

  const keysByName = keys as unknown as Record<string, string>
  const missingRequiredLlmKeys = requiredLlmUiKeys.filter((key) => !String(keysByName[key] ?? "").trim())
  const hasAllRequiredLlmKeys = missingRequiredLlmKeys.length === 0

  async function handleLaunch() {
    if (!hasAllRequiredLlmKeys) {
      setError(
        `Missing required LLM API key(s): ${missingRequiredLlmKeys.join(", ")}. Required keys are inferred from model prefixes in settings.yaml.`,
      )
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      saveApiKeys(keys)
      const req = buildRunRequest(yaml || defaultYaml, keys)
      if (csvFile && csvMode === "masterlist" && onSubmitWithMasterlistCsv) {
        await onSubmitWithMasterlistCsv(csvFile, req)
      } else if (csvFile && onSubmitWithSupplementaryCsv) {
        await onSubmitWithSupplementaryCsv(csvFile, req)
      } else {
        await onSubmit(req)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumb + Back */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onBack}
            disabled={isGeneratingConfig}
            className="text-muted hover:text-foreground hover:bg-surface-3/50 shrink-0 -ml-2"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Back
          </Button>
          <span className="text-muted">|</span>
          <span className="text-xs text-muted">
            <span className="text-intent-success/80 font-medium">1. Question</span>
            <span className="text-muted mx-1.5">/</span>
            <span className="text-intent-primary font-medium">2. Config</span>
          </span>
        </div>
        <div>
          <h2 className="text-base font-semibold text-foreground">Review Configuration</h2>
          {question && (
            <p className="text-xs text-muted mt-0.5 leading-relaxed truncate max-w-xl" title={question}>
              Generated for: {question}
            </p>
          )}
        </div>
      </div>

      {csvFile && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 bg-intent-info-subtle border border-intent-info-border rounded-xl text-xs text-intent-info">
          <Upload className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
          <span className="leading-relaxed">
            {csvMode === "masterlist" ? "Master list CSV" : "Supplementary CSV"}:{" "}
            <span className="font-medium text-intent-info-fg">{csvFile.name}</span>{" "}
            {csvMode === "masterlist"
              ? "will be used as the primary study list for this run."
              : "will be merged with connector search results before screening."}
          </span>
        </div>
      )}

      {/* Generated banner */}
      {question && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 bg-intent-success-subtle border border-intent-success-border rounded-xl text-xs text-foreground">
          <Sparkles className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
          <span className="leading-relaxed">
            {isGeneratingConfig
              ? "Building config from your research question. Progress is shown live below."
              : "Config generated from your research question. Edit the YAML below if needed, add your API keys, then launch."}
          </span>
        </div>
      )}

      <div className={`grid gap-4 items-start ${showGenerationSummary ? "grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)]" : "grid-cols-1"}`}>
        {showGenerationSummary && (
          <GenerationProgressCard
            activeStepKey={activeGenStep}
            stepMetadata={activeStepMetadata}
            usedWebFallback={usedWebFallback}
            fallbackReason={fallbackReason}
          />
        )}
        <PageSection
          icon={FileCode2}
          title="Review Config (YAML)"
          description={isGeneratingConfig ? "Generating YAML..." : "Edit any field before launching"}
        >
          <YamlEditor
            value={yaml}
            onChange={onYamlChange}
            placeholder="Paste your review.yaml content here..."
            rows={16}
            isLoading={isGeneratingConfig && !yaml.trim()}
            loadingLabel="Generating review YAML..."
          />
          <p className="label-muted mt-1.5">
            The YAML drives all phases of the review.
          </p>
        </PageSection>
      </div>

      {/* API Keys */}
      <PageSection
        icon={Key}
        title="API Keys"
        description={!hasAllRequiredLlmKeys ? `Required: ${requiredLlmUiKeys.join(", ")}` : undefined}
      >
        <SetupApiKeysSection keys={keys} onChange={setKeys} embedded />
      </PageSection>

      {/* Error */}
      {error && <FetchError message={error} onRetry={() => setError(null)} />}
      {generationError && (
        <FetchError message={generationError} onRetry={onRetryGeneration} />
      )}

      {/* Launch */}
      <Button
        type="button"
        onClick={() => void handleLaunch()}
        disabled={disabled || submitting || isGeneratingConfig || !yaml.trim() || !hasAllRequiredLlmKeys}
        className="w-full h-11 disabled:opacity-40 font-semibold gap-2 transition-colors"
      >
        {submitting ? (
          <>
            <Spinner size="sm" className="text-intent-primary-fg" />
            Starting...
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" />
            Launch Review
          </>
        )}
      </Button>
    </div>
  )
}
