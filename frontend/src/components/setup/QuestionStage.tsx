import { useEffect, useRef, useState } from "react"
import { ChevronDown, Clock, FileCode2, HeartPulse, RotateCcw, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner, FetchError } from "@/components/ui/feedback"
import { Textarea } from "@/components/ui/textarea"
import { formatShortDate } from "@/lib/format"
import { fetchEnvKeysStatus, fetchRequiredLlmUiKeys, loadApiKeys } from "@/lib/api"
import type { EnvKeysStatus, HistoryEntry } from "@/lib/api"
import type { ConfigGenerateRequest, CsvMode, GenerationProfile } from "./types"
import { CsvDropZone } from "./CsvDropZone"

interface QuestionStageProps {
  onGenerateRequested: (req: ConfigGenerateRequest) => void
  onPasteYaml: () => void
  history: HistoryEntry[]
  onLoadFromHistory: (entry: HistoryEntry) => void
  loadingHistoryId: string | null
  loadError: string | null
  onClearError: () => void
  initialQuestion: string
  initialFireworksKey: string
  initialCsvFile: File | null
  initialCsvMode: CsvMode
}

export function QuestionStage({
  onGenerateRequested,
  onPasteYaml,
  history,
  onLoadFromHistory,
  loadingHistoryId,
  loadError,
  onClearError,
  initialQuestion,
  initialFireworksKey,
  initialCsvFile,
  initialCsvMode,
}: QuestionStageProps) {
  const [question, setQuestion] = useState(initialQuestion)
  const [envStatus, setEnvStatus] = useState<EnvKeysStatus | null>(null)
  const [requiredUiKeys, setRequiredUiKeys] = useState<string[]>(["fireworks"])
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    fetchEnvKeysStatus().then((status) => {
      if (!status) return
      setEnvStatus(status)
    })
    fetchRequiredLlmUiKeys().then((keys) => {
      if (keys.length > 0) {
        setRequiredUiKeys(keys)
      }
    })
  }, [])

  function hasRequiredCredentials(): boolean {
    const saved = loadApiKeys()
    const savedByName = (saved ?? {}) as Record<string, string>
    const required = requiredUiKeys.length > 0 ? requiredUiKeys : ["fireworks"]
    return required.every((key) => {
      const browserVal = String(savedByName[key] ?? "").trim()
      const envConfigured = envStatus?.providers[key]?.configured ?? false
      const initialVal = key === "fireworks" ? initialFireworksKey?.trim() ?? "" : ""
      return !!browserVal || envConfigured || !!initialVal
    })
  }

  const hasCredentials = hasRequiredCredentials()
  const visibleSubmitError = hasCredentials ? null : submitError

  const [showHistory, setShowHistory] = useState(false)
  const [healthSdgEnabled, setHealthSdgEnabled] = useState(false)
  const [csvFile, setCsvFile] = useState<File | null>(initialCsvFile)
  const [csvMode, setCsvMode] = useState<CsvMode>(initialCsvMode)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const activeProfile: GenerationProfile = healthSdgEnabled ? "health_sdg" : "standard"

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowHistory(false)
      }
    }
    if (showHistory) document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showHistory])

  async function handleGenerate() {
    if (!question.trim()) return
    if (!hasRequiredCredentials()) {
      setSubmitError("Add at least one LLM API key in Settings before generating a config.")
      return
    }
    setSubmitError(null)
    const savedKey = loadApiKeys()?.fireworks ?? ""
    onGenerateRequested({
      question: question.trim(),
      fireworksKey: envStatus?.server_ready ? "" : (initialFireworksKey || savedKey).trim(),
      csvFile: csvFile ?? undefined,
      csvMode,
      generationProfile: activeProfile,
    })
  }

  const completedRuns = history.filter((h) => h.status === "completed").slice(0, 10)
  const canGenerate = !!question.trim()

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <div className="text-center pt-4 pb-1">
        <p className="text-sm text-muted max-w-sm mx-auto leading-relaxed">
          Describe your review question to generate PICO, search keywords, and screening criteria.
        </p>
      </div>

      {/* Research question */}
      <div>
        <Textarea
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value)
            if (submitError) setSubmitError(null)
          }}
          rows={3}
          placeholder="What is the effect of [intervention] on [outcome] in [population]?"
          className="resize-none text-sm bg-card border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void handleGenerate()
          }}
        />
        <p className="text-xs text-muted mt-1.5">Press Cmd/Ctrl+Enter to generate config.</p>
      </div>

      <CsvDropZone file={csvFile} onFile={setCsvFile} mode={csvMode} onModeChange={setCsvMode} />

      {loadError && (
        <FetchError message={loadError} onRetry={onClearError} />
      )}
      {visibleSubmitError && (
        <FetchError message={visibleSubmitError} onRetry={() => setSubmitError(null)} />
      )}

      {/* CTA */}
      <div className="space-y-3">
        <Button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={!canGenerate}
          className="w-full h-11 disabled:opacity-40 font-semibold gap-2 transition-colors"
        >
          <Sparkles className="h-4 w-4" />
          Generate Config
        </Button>
        <button
          type="button"
          role="checkbox"
          aria-checked={healthSdgEnabled}
          onClick={() => setHealthSdgEnabled((v) => !v)}
          className="flex w-full items-start gap-2.5 rounded-lg border border-border bg-surface-2/50 px-3 py-2.5 text-left transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-intent-primary-border"
        >
          <span
            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
              healthSdgEnabled
                ? "border-intent-primary-border bg-intent-primary-subtle text-foreground"
                : "border-border bg-card text-transparent"
            }`}
            aria-hidden
          >
            <span className="text-[10px] font-bold leading-none">✓</span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <HeartPulse className="h-3.5 w-3.5 text-intent-success shrink-0" />
              Health + SDG alignment
            </span>
            <span className="mt-0.5 block text-[11px] text-muted leading-relaxed">
              Adds health-impact pathways and UN SDG alignment to the generated config.
            </span>
          </span>
        </button>
      </div>

      {/* Secondary actions */}
      <div className="flex items-center justify-between pt-1">
        <div className="relative" ref={dropdownRef}>
          {completedRuns.length > 0 && (
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              disabled={!!loadingHistoryId}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
            >
              {loadingHistoryId ? (
                <Spinner size="sm" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
              {loadingHistoryId ? "Loading..." : "Reuse past config"}
              <ChevronDown className={`h-3 w-3 transition-transform ${showHistory ? "rotate-180" : ""}`} />
            </button>
          )}

          {showHistory && (
            <div className="absolute left-0 top-full mt-1.5 z-20 w-[min(400px,calc(100vw-2rem))] max-h-[280px] overflow-y-auto glass-panel border border-border/80 rounded-xl shadow-xl">
              <div className="px-3 py-2 border-b border-border">
                <p className="text-xs text-muted">Select a completed run to reuse its config</p>
              </div>
              {completedRuns.map((entry) => (
                <button
                  key={entry.workflow_id}
                  type="button"
                  onClick={() => {
                    setShowHistory(false)
                    onLoadFromHistory(entry)
                  }}
                  className="w-full flex items-start gap-2.5 px-3 py-2.5 hover:bg-surface-2/60 transition-colors text-left border-b border-border/50 last:border-0"
                >
                  <Clock className="h-3.5 w-3.5 text-muted mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-foreground truncate leading-snug">{entry.topic}</p>
                    <p className="text-xs text-muted mt-0.5">{formatShortDate(entry.created_at)}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onPasteYaml}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
        >
          <FileCode2 className="h-3.5 w-3.5" />
          Paste YAML
        </button>
      </div>
    </div>
  )
}
