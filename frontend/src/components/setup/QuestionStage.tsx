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
  initialDeepseekKey: string
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
  initialDeepseekKey,
  initialCsvFile,
  initialCsvMode,
}: QuestionStageProps) {
  const [question, setQuestion] = useState(initialQuestion)
  const [envStatus, setEnvStatus] = useState<EnvKeysStatus | null>(null)
  const [requiredUiKeys, setRequiredUiKeys] = useState<string[]>(["deepseek"])
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
    const required = requiredUiKeys.length > 0 ? requiredUiKeys : ["deepseek"]
    return required.every((key) => {
      const browserVal = String(savedByName[key] ?? "").trim()
      const envConfigured = envStatus?.providers[key]?.configured ?? false
      const initialVal = key === "deepseek" ? initialDeepseekKey?.trim() ?? "" : ""
      return !!browserVal || envConfigured || !!initialVal
    })
  }

  const hasCredentials = hasRequiredCredentials()
  const visibleSubmitError = hasCredentials ? null : submitError

  const [showHistory, setShowHistory] = useState(false)
  const [csvFile, setCsvFile] = useState<File | null>(initialCsvFile)
  const [csvMode, setCsvMode] = useState<CsvMode>(initialCsvMode)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowHistory(false)
      }
    }
    if (showHistory) document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showHistory])

  async function handleGenerate(generationProfile: GenerationProfile = "standard") {
    if (!question.trim()) return
    if (!hasRequiredCredentials()) {
      setSubmitError("Add at least one LLM API key in Settings before generating a config.")
      return
    }
    setSubmitError(null)
    const savedKey = loadApiKeys()?.deepseek ?? ""
    onGenerateRequested({
      question: question.trim(),
      deepseekKey: envStatus?.server_ready ? "" : (initialDeepseekKey || savedKey).trim(),
      csvFile: csvFile ?? undefined,
      csvMode,
      generationProfile,
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
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void handleGenerate("standard")
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
      <div className="space-y-2.5">
        <div className="grid grid-cols-2 gap-2.5">
        <Button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={!canGenerate}
          className="h-11 disabled:opacity-40 font-semibold gap-2 transition-colors"
        >
          <Sparkles className="h-4 w-4" />
          Generate Config
        </Button>
        <Button
          type="button"
          onClick={() => void handleGenerate("health_sdg")}
          disabled={!canGenerate}
          variant="success"
          className="h-11 disabled:opacity-40 font-semibold gap-2 transition-colors"
        >
          <HeartPulse className="h-4.5 w-4.5" />
          Health + SDG Config
        </Button>
        </div>
        <p className="text-[11px] text-muted text-center leading-relaxed">
          Health mode adds health-impact pathways and UN SDG alignment.
        </p>
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
