import { useEffect, useId, useState } from "react"
import { FileCode2, HeartPulse, KeyRound, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { FetchError } from "@/components/ui/feedback"
import { useSettings } from "@/context/SettingsContext"
import { fetchEnvKeysStatus, fetchRequiredLlmUiKeys, llmProviderLabel, loadApiKeys } from "@/lib/api"
import type { EnvKeysStatus, HistoryEntry } from "@/lib/api"
import type { ConfigGenerateRequest, CsvMode, ReviewTypeChoice } from "./types"
import { CsvDropZone } from "./CsvDropZone"
import { ReviewTypeCards } from "./ReviewTypeCards"
import { ReviewTypeDecisionStage } from "./ReviewTypeDecisionStage"
import { ReuseConfigPopover } from "./ReuseConfigPopover"
import { takePendingSetupQuestion } from "@/lib/pendingSetupQuestion"

function questionFrameworkForReviewType(reviewType: ReviewTypeChoice): "PICO" | "PCC" {
  return reviewType === "scoping" ? "PCC" : "PICO"
}

function missingProviderKeys(requiredUiKeys: string[], envStatus: EnvKeysStatus | null): string[] {
  const saved = (loadApiKeys() ?? {}) as Record<string, string>
  const required = requiredUiKeys.length > 0 ? requiredUiKeys : ["fireworks"]
  return required.filter((key) => {
    const browserVal = String(saved[key] ?? "").trim()
    const envConfigured = envStatus?.providers[key]?.configured ?? false
    return !browserVal && !envConfigured
  })
}

interface QuestionStageProps {
  onGenerateRequested: (req: ConfigGenerateRequest) => void
  onPasteYaml: () => void
  history: HistoryEntry[]
  onLoadFromHistory: (entry: HistoryEntry) => void
  loadingHistoryId: string | null
  loadError: string | null
  onClearError: () => void
  disabled?: boolean
}

export function QuestionStage({
  onGenerateRequested,
  onPasteYaml,
  history,
  onLoadFromHistory,
  loadingHistoryId,
  loadError,
  onClearError,
  disabled = false,
}: QuestionStageProps) {
  const questionId = useId()
  const questionHintId = useId()
  const reviewTypeLabelId = useId()
  const [question, setQuestion] = useState(takePendingSetupQuestion)
  const [reviewType, setReviewType] = useState<ReviewTypeChoice | null>(null)
  const [quizOpen, setQuizOpen] = useState(false)
  const [envStatus, setEnvStatus] = useState<EnvKeysStatus | null>(null)
  const [keysChecked, setKeysChecked] = useState(false)
  const [requiredUiKeys, setRequiredUiKeys] = useState<string[]>(["fireworks"])
  const { openSettings, closedVersion: settingsClosedVersion } = useSettings()
  const [healthSdgEnabled, setHealthSdgEnabled] = useState(false)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvMode, setCsvMode] = useState<CsvMode>("supplementary")

  useEffect(() => {
    let cancelled = false
    void Promise.all([fetchEnvKeysStatus(), fetchRequiredLlmUiKeys()]).then(([status, keys]) => {
      if (cancelled) return
      if (status) setEnvStatus(status)
      if (keys.length > 0) setRequiredUiKeys(keys)
      setKeysChecked(true)
    })
    return () => {
      cancelled = true
    }
  }, [settingsClosedVersion])

  const missingKeys = keysChecked && !envStatus?.server_ready ? missingProviderKeys(requiredUiKeys, envStatus) : []
  const trimmedQuestion = question.trim()
  const canGenerate = !disabled && !!trimmedQuestion && reviewType !== null && missingKeys.length === 0
  const blockingHint = disabled
    ? null
    : !trimmedQuestion
      ? "Enter a research question to continue."
      : reviewType === null
        ? "Choose a review type to continue."
        : null

  function handleGenerate() {
    if (!canGenerate || reviewType === null) return
    onGenerateRequested({
      question: trimmedQuestion,
      fireworksKey: envStatus?.server_ready ? "" : (loadApiKeys()?.fireworks ?? "").trim(),
      csvFile: csvFile ?? undefined,
      csvMode,
      generationProfile: healthSdgEnabled ? "health_sdg" : "standard",
      reviewType,
      questionFramework: questionFrameworkForReviewType(reviewType),
    })
  }

  const questionPlaceholder =
    reviewType === "scoping"
      ? "What is known about [concept] in [population] in [context]?"
      : "What is the effect of [intervention] on [outcome] in [population]?"
  const questionHint =
    reviewType === "scoping"
      ? "We turn it into PCC (population, concept, context), search keywords, and screening criteria."
      : "We turn it into PICO, search keywords, and screening criteria. Press Cmd/Ctrl+Enter to generate."

  return (
    <div className="flex flex-col gap-6">
      <section className="space-y-1.5">
        <label htmlFor={questionId} className="text-sm font-medium text-foreground">
          Research question
        </label>
        <Textarea
          id={questionId}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          placeholder={questionPlaceholder}
          aria-describedby={questionHintId}
          className="resize-y text-sm bg-card border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleGenerate()
          }}
        />
        <p id={questionHintId} className="text-xs text-muted">{questionHint}</p>
      </section>

      <section className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h2 id={reviewTypeLabelId} className="text-sm font-medium text-foreground">Review type</h2>
          {!quizOpen && (
            <button
              type="button"
              onClick={() => setQuizOpen(true)}
              className="rounded-sm text-xs text-intent-primary-text underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Help me decide
            </button>
          )}
        </div>
        {quizOpen ? (
          <ReviewTypeDecisionStage
            onCancel={() => setQuizOpen(false)}
            onComplete={(type) => {
              setReviewType(type)
              setQuizOpen(false)
            }}
          />
        ) : (
          <ReviewTypeCards value={reviewType} onChange={setReviewType} disabled={disabled} labelledBy={reviewTypeLabelId} />
        )}
      </section>

      <section className="space-y-3" aria-label="Options">
        <label className="flex w-full cursor-pointer items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5 transition-colors hover:bg-surface-2 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring">
          <input
            type="checkbox"
            checked={healthSdgEnabled}
            onChange={(e) => setHealthSdgEnabled(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-intent-primary"
          />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <HeartPulse className="h-3.5 w-3.5 text-intent-success shrink-0" aria-hidden />
              Health + SDG alignment
            </span>
            <span className="mt-0.5 block text-2xs text-muted leading-relaxed">
              Adds health-impact pathways and UN SDG alignment to the generated config.
            </span>
          </span>
        </label>

        <CsvDropZone file={csvFile} onFile={setCsvFile} mode={csvMode} onModeChange={setCsvMode} />

        <div className="flex flex-wrap items-center gap-2">
          <ReuseConfigPopover
            history={history}
            onSelect={onLoadFromHistory}
            loadingHistoryId={loadingHistoryId}
            disabled={disabled}
          />
          <span className="text-xs text-muted">Start from a config you used before.</span>
        </div>
      </section>

      {loadError && <FetchError message={loadError} onDismiss={onClearError} />}

      {missingKeys.length > 0 && (
        <div
          role="alert"
          data-testid="missing-api-key-banner"
          className="flex flex-col gap-2 rounded-lg border border-intent-warning-border bg-intent-warning-subtle px-3 py-2.5 text-xs text-intent-warning-text min-[480px]:flex-row min-[480px]:items-center"
        >
          <span className="flex flex-1 min-w-0 items-start gap-2">
            <KeyRound className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="min-w-0">
              Missing API key: {missingKeys.map(llmProviderLabel).join(", ")}. Add it before generating a config.
            </span>
          </span>
          <Button
            type="button"
            size="xs"
            variant="outline"
            onClick={() => openSettings("keys")}
            className="self-start shrink-0 ml-5.5 min-[480px]:ml-0 min-[480px]:self-auto"
          >
            Open Settings → Keys
          </Button>
        </div>
      )}

      <div className="space-y-2">
        <Button
          type="button"
          onClick={handleGenerate}
          disabled={!canGenerate}
          size="lg"
          className="w-full font-semibold"
        >
          <Sparkles />
          Generate config
        </Button>
        {blockingHint && <p className="text-center text-xs text-muted">{blockingHint}</p>}
      </div>

      <div className="flex justify-center">
        <Button
          type="button"
          variant="ghost"
          size="xs"
          onClick={onPasteYaml}
          disabled={disabled}
          className="text-muted hover:text-foreground"
        >
          <FileCode2 />
          Paste YAML instead
        </Button>
      </div>
    </div>
  )
}
