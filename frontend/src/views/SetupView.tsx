import { useState, useEffect, useRef } from "react"
import {
  ChevronDown,
  ChevronLeft,
  Clock,
  Eye,
  EyeOff,
  RotateCcw,
  Sparkles,
  Wand2,
  FileCode2,
  Key,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  fetchHistory,
  fetchRunConfig,
  generateConfig,
  loadApiKeys,
  saveApiKeys,
} from "@/lib/api"
import { FetchError } from "@/components/ui/feedback"
import { formatShortDate } from "@/lib/format"
import type { HistoryEntry, RunRequest, StoredApiKeys } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SetupViewProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

type Stage = "question" | "review"

// ---------------------------------------------------------------------------
// Generation steps (shown while AI is working)
// ---------------------------------------------------------------------------

const GEN_STEPS = [
  { label: "Analyzing your research question", detail: "Understanding scope, domain, and intent" },
  { label: "Defining PICO framework", detail: "Population, Intervention, Comparison, Outcome" },
  { label: "Generating search keywords", detail: "20+ terms covering synonyms and brand names" },
  { label: "Writing inclusion criteria", detail: "Specifying eligible study types and settings" },
  { label: "Writing exclusion criteria", detail: "Filtering out irrelevant or low-quality sources" },
  { label: "Finalizing domain and scope", detail: "Summarizing coverage and boundaries" },
]

const STEP_DURATIONS = [1500, 2200, 2200, 2000, 2000]

function GeneratingScreen() {
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const timeouts: ReturnType<typeof setTimeout>[] = []
    let elapsed = 0
    for (let i = 0; i < STEP_DURATIONS.length; i++) {
      elapsed += STEP_DURATIONS[i]
      const nextStep = i + 1
      const t = setTimeout(() => setActiveStep(nextStep), elapsed)
      timeouts.push(t)
    }
    return () => timeouts.forEach(clearTimeout)
  }, [])

  return (
    <div className="flex flex-col items-center py-8 gap-6">
      <div className="relative flex items-center justify-center">
        <div className="absolute w-16 h-16 rounded-full bg-violet-500/10 animate-ping" />
        <div className="absolute w-12 h-12 rounded-full bg-violet-500/15 animate-pulse" />
        <div className="relative w-10 h-10 rounded-xl bg-violet-600/30 border border-violet-500/40 flex items-center justify-center">
          <Wand2 className="h-5 w-5 text-violet-400" />
        </div>
      </div>

      <div className="text-center">
        <p className="text-sm font-semibold text-zinc-200 mb-0.5">Generating your review config</p>
        <p className="text-xs text-zinc-500">Usually 20-30 seconds</p>
      </div>

      <div className="w-full flex flex-col gap-1.5">
        {GEN_STEPS.map((step, i) => {
          const done = i < activeStep
          const active = i === activeStep
          return (
            <div
              key={i}
              className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border transition-all duration-500 ${
                done
                  ? "bg-emerald-500/8 border-emerald-500/20"
                  : active
                  ? "bg-violet-500/10 border-violet-500/30"
                  : "bg-zinc-900/40 border-zinc-800/60"
              }`}
            >
              <div className="flex-shrink-0 mt-0.5">
                {done ? (
                  <div className="w-4 h-4 rounded-full bg-emerald-500/30 border border-emerald-400/50 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  </div>
                ) : active ? (
                  <div className="w-4 h-4 rounded-full border border-violet-400/60 flex items-center justify-center">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
                  </div>
                ) : (
                  <div className="w-4 h-4 rounded-full border border-zinc-700" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-xs font-medium leading-snug ${
                  done ? "text-emerald-300/80" : active ? "text-violet-200" : "text-zinc-600"
                }`}>
                  {step.label}
                </p>
                {(active || done) && (
                  <p className={`text-xs mt-0.5 leading-snug ${
                    done ? "text-emerald-400/50" : "text-zinc-500"
                  }`}>
                    {step.detail}
                  </p>
                )}
                {active && i === GEN_STEPS.length - 1 && (
                  <p className="text-xs mt-1 text-violet-400/70 animate-pulse leading-snug">
                    Searching the web and building your config...
                  </p>
                )}
              </div>
              {active && i < GEN_STEPS.length - 1 && (
                <div className="flex gap-0.5 mt-1 flex-shrink-0">
                  {[0, 1, 2].map((d) => (
                    <div
                      key={d}
                      className="w-1 h-1 rounded-full bg-violet-400/60 animate-bounce"
                      style={{ animationDelay: `${d * 150}ms` }}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// API Keys section (inline, used in Stage 2 before launching)
// ---------------------------------------------------------------------------

interface ApiKeysProps {
  keys: StoredApiKeys
  onChange: (k: StoredApiKeys) => void
}

function ApiKeysSection({ keys, onChange }: ApiKeysProps) {
  const [expanded, setExpanded] = useState(false)
  const [showGemini, setShowGemini] = useState(false)

  const fields: { id: keyof StoredApiKeys; label: string; placeholder: string; required?: boolean }[] = [
    { id: "gemini", label: "Gemini API Key", placeholder: "AIza...", required: true },
    { id: "openalex", label: "OpenAlex Email", placeholder: "user@example.com" },
    { id: "pubmedEmail", label: "PubMed Email", placeholder: "user@example.com" },
    { id: "pubmedApiKey", label: "PubMed API Key", placeholder: "optional -- increases rate limits" },
    { id: "ieee", label: "IEEE Xplore API Key", placeholder: "optional" },
    { id: "perplexity", label: "Perplexity API Key", placeholder: "pplx-..." },
    { id: "semanticScholar", label: "Semantic Scholar API Key", placeholder: "optional" },
    { id: "crossrefEmail", label: "Crossref Email", placeholder: "user@example.com" },
  ]

  const primaryField = fields[0]
  const extraFields = fields.slice(1)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
        <Key className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
        <span className="text-xs font-semibold text-zinc-300 flex-1">API Keys</span>
        {!keys.gemini && (
          <span className="text-[10px] text-red-400 font-medium">Gemini key required</span>
        )}
      </div>

      <div className="px-4 py-4 space-y-3">
        {/* Gemini key -- always shown */}
        <div>
          <label className="block text-xs font-medium text-zinc-400 mb-1.5">
            {primaryField.label} <span className="text-red-500">*</span>
          </label>
          <div className="relative">
            <Input
              type={showGemini ? "text" : "password"}
              value={keys.gemini}
              onChange={(e) => onChange({ ...keys, gemini: e.target.value })}
              placeholder={primaryField.placeholder}
              autoComplete="off"
              className="pr-9 h-9 text-xs bg-zinc-950 border-zinc-700 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
            />
            <button
              type="button"
              onClick={() => setShowGemini((v) => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              {showGemini ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {/* Optional keys toggle */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
          {expanded ? "Hide optional API keys" : "Add optional API keys (OpenAlex, PubMed, IEEE...)"}
        </button>

        {expanded && extraFields.map((f) => (
          <div key={f.id}>
            <label className="block text-xs font-medium text-zinc-500 mb-1">
              {f.label}
            </label>
            <Input
              type="text"
              value={keys[f.id]}
              onChange={(e) => onChange({ ...keys, [f.id]: e.target.value })}
              placeholder={f.placeholder}
              autoComplete="off"
              className="h-9 text-xs bg-zinc-950 border-zinc-700 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage 1 -- Question input
// ---------------------------------------------------------------------------

interface Stage1Props {
  onGenerated: (yaml: string, question: string) => void
  onPasteYaml: () => void
  history: HistoryEntry[]
  onLoadFromHistory: (entry: HistoryEntry) => void
  loadingHistoryId: string | null
  loadError: string | null
  onClearError: () => void
}

function QuestionStage({
  onGenerated,
  onPasteYaml,
  history,
  onLoadFromHistory,
  loadingHistoryId,
  loadError,
  onClearError,
}: Stage1Props) {
  const [question, setQuestion] = useState("")
  const [geminiKey, setGeminiKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const stored = loadApiKeys()
    if (stored?.gemini) setGeminiKey(stored.gemini)
  }, [])

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
    if (!question.trim() || !geminiKey.trim()) return
    setError(null)
    setGenerating(true)
    try {
      const yaml = await generateConfig(question.trim(), geminiKey.trim())
      onGenerated(yaml, question.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setGenerating(false)
    }
  }

  if (generating) {
    return <GeneratingScreen />
  }

  const completedRuns = history.filter((h) => h.status === "completed").slice(0, 10)

  return (
    <div className="flex flex-col gap-5">
      {/* Hero */}
      <div className="text-center pt-6 pb-2">
        <div className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-violet-600/20 border border-violet-500/30 mb-4">
          <Wand2 className="h-5 w-5 text-violet-400" />
        </div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">New Systematic Review</h2>
        <p className="text-sm text-zinc-500 max-w-sm mx-auto leading-relaxed">
          Describe your research question. We generate the PICO framework, search keywords,
          inclusion and exclusion criteria automatically.
        </p>
      </div>

      {/* Research question */}
      <div>
        <label className="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide">
          Research Question
        </label>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          placeholder="e.g. What is the impact of autonomous UV-C disinfection robots on pathogen reduction and healthcare-associated infection rates in hospital settings?"
          className="resize-none text-sm bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50 leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void handleGenerate()
          }}
        />
        <p className="text-xs text-zinc-600 mt-1.5">Cmd+Enter to generate</p>
      </div>

      {/* Gemini key */}
      <div>
        <label className="block text-xs font-semibold text-zinc-400 mb-2 uppercase tracking-wide">
          Gemini API Key <span className="text-red-500">*</span>
        </label>
        <div className="relative">
          <Input
            type={showKey ? "text" : "password"}
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
            placeholder="AIza..."
            autoComplete="off"
            className="pr-9 h-10 text-sm bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
        <p className="text-xs text-zinc-600 mt-1.5">
          Used to generate the config. You will confirm this key again before launching.
        </p>
      </div>

      {/* Error */}
      {error && (
        <FetchError message={error} onRetry={() => setError(null)} />
      )}
      {loadError && (
        <FetchError message={loadError} onRetry={onClearError} />
      )}

      {/* CTA */}
      <Button
        type="button"
        onClick={() => void handleGenerate()}
        disabled={!question.trim() || !geminiKey.trim()}
        className="w-full h-11 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold gap-2 transition-colors"
      >
        <Sparkles className="h-4 w-4" />
        Generate Review Config
      </Button>

      {/* Secondary actions */}
      <div className="flex items-center justify-between pt-1">
        {/* Load from past run */}
        <div className="relative" ref={dropdownRef}>
          {completedRuns.length > 0 && (
            <button
              type="button"
              onClick={() => setShowHistory((v) => !v)}
              disabled={!!loadingHistoryId}
              className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              <RotateCcw className={`h-3.5 w-3.5 ${loadingHistoryId ? "animate-spin" : ""}`} />
              {loadingHistoryId ? "Loading..." : "Load config from a past run"}
              <ChevronDown className={`h-3 w-3 transition-transform ${showHistory ? "rotate-180" : ""}`} />
            </button>
          )}

          {showHistory && (
            <div className="absolute left-0 top-full mt-1.5 z-20 w-[400px] max-h-[280px] overflow-y-auto bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl">
              <div className="px-3 py-2 border-b border-zinc-800">
                <p className="text-xs text-zinc-500">Select a completed run to reuse its config</p>
              </div>
              {completedRuns.map((entry) => (
                <button
                  key={entry.workflow_id}
                  type="button"
                  onClick={() => {
                    setShowHistory(false)
                    onLoadFromHistory(entry)
                  }}
                  className="w-full flex items-start gap-2.5 px-3 py-2.5 hover:bg-zinc-800/60 transition-colors text-left border-b border-zinc-800/50 last:border-0"
                >
                  <Clock className="h-3.5 w-3.5 text-zinc-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate leading-snug">{entry.topic}</p>
                    <p className="text-xs text-zinc-600 mt-0.5">{formatShortDate(entry.created_at)}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Skip to YAML */}
        <button
          type="button"
          onClick={onPasteYaml}
          className="flex items-center gap-1.5 text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <FileCode2 className="h-3.5 w-3.5" />
          Paste YAML directly
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage 2 -- Config review + API keys + Launch
// ---------------------------------------------------------------------------

interface Stage2Props {
  yaml: string
  onYamlChange: (y: string) => void
  question: string | null
  onBack: () => void
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
  defaultYaml: string
}

function ConfigReviewStage({
  yaml,
  onYamlChange,
  question,
  onBack,
  onSubmit,
  disabled,
  defaultYaml,
}: Stage2Props) {
  const [keys, setKeys] = useState<StoredApiKeys>({
    gemini: "",
    openalex: "",
    ieee: "",
    pubmedEmail: "",
    pubmedApiKey: "",
    perplexity: "",
    semanticScholar: "",
    crossrefEmail: "",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const stored = loadApiKeys()
    if (stored) setKeys(stored)
  }, [])

  async function handleLaunch() {
    if (!keys.gemini.trim()) {
      setError("Gemini API key is required to start a review.")
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      saveApiKeys(keys)
      await onSubmit({
        review_yaml: yaml || defaultYaml,
        gemini_api_key: keys.gemini,
        openalex_api_key: keys.openalex || undefined,
        ieee_api_key: keys.ieee || undefined,
        pubmed_email: keys.pubmedEmail || undefined,
        pubmed_api_key: keys.pubmedApiKey || undefined,
        perplexity_api_key: keys.perplexity || undefined,
        semantic_scholar_api_key: keys.semanticScholar || undefined,
        crossref_email: keys.crossrefEmail || undefined,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-zinc-100">Review Configuration</h2>
          {question && (
            <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed truncate max-w-md" title={question}>
              Generated for: {question}
            </p>
          )}
        </div>
      </div>

      {/* Generated banner */}
      {question && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-xs text-emerald-400">
          <Sparkles className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
          <span className="leading-relaxed">
            Config generated from your research question. Edit the YAML below if needed, add your API keys, then launch.
          </span>
        </div>
      )}

      {/* YAML editor */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <FileCode2 className="h-3.5 w-3.5 text-zinc-500" />
          <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wide">
            Review Config (YAML)
          </label>
        </div>
        <Textarea
          value={yaml}
          onChange={(e) => onYamlChange(e.target.value)}
          rows={16}
          placeholder="Paste your review.yaml content here..."
          className="resize-none text-xs font-mono bg-zinc-950 border-zinc-800 text-zinc-300 placeholder:text-zinc-600 focus-visible:ring-violet-500/50 leading-relaxed"
          spellCheck={false}
        />
        <p className="text-xs text-zinc-600 mt-1.5">
          Edit any field before launching. The YAML drives all phases of the review.
        </p>
      </div>

      {/* API Keys */}
      <ApiKeysSection keys={keys} onChange={setKeys} />

      {/* Error */}
      {error && <FetchError message={error} onRetry={() => setError(null)} />}

      {/* Launch */}
      <Button
        type="button"
        onClick={() => void handleLaunch()}
        disabled={disabled || submitting || !keys.gemini.trim()}
        className="w-full h-11 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold gap-2 transition-colors"
      >
        {submitting ? (
          <>
            <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
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

// ---------------------------------------------------------------------------
// Main SetupView
// ---------------------------------------------------------------------------

export function SetupView({ defaultReviewYaml, onSubmit, disabled }: SetupViewProps) {
  const [stage, setStage] = useState<Stage>("question")
  const [generatedYaml, setGeneratedYaml] = useState("")
  const [researchQuestion, setResearchQuestion] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    fetchHistory().then(setHistory).catch(() => setHistory([]))
  }, [])

  function handleGenerated(yaml: string, question: string) {
    setGeneratedYaml(yaml)
    setResearchQuestion(question)
    setStage("review")
  }

  function handlePasteYaml() {
    setGeneratedYaml(defaultReviewYaml)
    setResearchQuestion(null)
    setStage("review")
  }

  async function handleLoadFromHistory(entry: HistoryEntry) {
    setLoadError(null)
    setLoadingHistoryId(entry.workflow_id)
    try {
      const yaml = await fetchRunConfig(entry.workflow_id)
      if (!yaml) {
        setLoadError(
          `Config not saved for that run. Only runs started recently can be reloaded.`
        )
        return
      }
      setGeneratedYaml(yaml)
      setResearchQuestion(entry.topic)
      setStage("review")
    } catch {
      setLoadError("Failed to load config for that run.")
    } finally {
      setLoadingHistoryId(null)
    }
  }

  return (
    <div className="max-w-xl mx-auto pt-4 pb-16">
      {stage === "question" ? (
        <QuestionStage
          onGenerated={handleGenerated}
          onPasteYaml={handlePasteYaml}
          history={history}
          onLoadFromHistory={(entry) => void handleLoadFromHistory(entry)}
          loadingHistoryId={loadingHistoryId}
          loadError={loadError}
          onClearError={() => setLoadError(null)}
        />
      ) : (
        <ConfigReviewStage
          yaml={generatedYaml}
          onYamlChange={setGeneratedYaml}
          question={researchQuestion}
          onBack={() => {
            setStage("question")
            setLoadError(null)
          }}
          onSubmit={onSubmit}
          disabled={disabled}
          defaultYaml={defaultReviewYaml}
        />
      )}
    </div>
  )
}
