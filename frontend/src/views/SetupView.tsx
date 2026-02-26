import { useState, useEffect, useRef } from "react"
import { ChevronDown, Clock, Eye, EyeOff, RotateCcw, Sparkles, Wand2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { RunForm } from "@/components/RunForm"
import { fetchHistory, fetchRunConfig, generateConfig, loadApiKeys } from "@/lib/api"
import type { HistoryEntry, RunRequest } from "@/lib/api"

type Mode = "ai" | "yaml" | "manual"

interface SetupViewProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

function formatDate(iso: string): string {
  if (!iso) return ""
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
  } catch {
    return iso.slice(0, 10)
  }
}

// ---------------------------------------------------------------------------
// Mode pill selector
// ---------------------------------------------------------------------------

interface ModeSelectorProps {
  mode: Mode
  onSelect: (m: Mode) => void
}

function ModeSelector({ mode, onSelect }: ModeSelectorProps) {
  const modes: Array<{ id: Mode; label: string; desc: string }> = [
    { id: "ai", label: "AI Generate", desc: "Enter a research question, we fill everything" },
    { id: "yaml", label: "YAML", desc: "Paste or edit the config YAML directly" },
    { id: "manual", label: "Manual", desc: "Fill out each field yourself" },
  ]
  return (
    <div className="flex gap-1 p-1 bg-zinc-900 border border-zinc-800 rounded-xl mb-5">
      {modes.map((m) => (
        <button
          key={m.id}
          type="button"
          onClick={() => onSelect(m.id)}
          title={m.desc}
          className={`flex-1 text-xs py-2 px-3 rounded-lg font-medium transition-all ${
            mode === m.id
              ? "bg-violet-600/25 border border-violet-500/40 text-violet-200"
              : "text-zinc-500 hover:text-zinc-300 border border-transparent"
          }`}
        >
          {m.id === "ai" && <Sparkles className="inline h-3 w-3 mr-1 -mt-px opacity-70" />}
          {m.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generation steps for the loading screen
// ---------------------------------------------------------------------------

const GEN_STEPS = [
  { label: "Analyzing your research question", detail: "Understanding scope, domain, and intent" },
  { label: "Defining PICO framework", detail: "Population, Intervention, Comparison, Outcome" },
  { label: "Generating search keywords", detail: "20+ terms covering synonyms and brand names" },
  { label: "Writing inclusion criteria", detail: "Specifying eligible study types and settings" },
  { label: "Writing exclusion criteria", detail: "Filtering out irrelevant or low-quality sources" },
  { label: "Finalizing domain and scope", detail: "Summarizing coverage and boundaries" },
]

// Approximate ms each step takes (total ~15s spread across steps)
const STEP_DURATIONS = [1800, 2800, 2600, 2400, 2400, 2000]

function GeneratingScreen() {
  const [activeStep, setActiveStep] = useState(0)
  const [doneSteps, setDoneSteps] = useState<Set<number>>(new Set())

  useEffect(() => {
    let step = 0
    let timeout: ReturnType<typeof setTimeout>

    function advance() {
      if (step >= GEN_STEPS.length - 1) return
      setDoneSteps((prev) => new Set([...prev, step]))
      step++
      setActiveStep(step)
      timeout = setTimeout(advance, STEP_DURATIONS[step] ?? 2000)
    }

    timeout = setTimeout(advance, STEP_DURATIONS[0])
    return () => clearTimeout(timeout)
  }, [])

  return (
    <div className="flex flex-col items-center py-6 gap-6">
      {/* Pulsing icon */}
      <div className="relative flex items-center justify-center">
        <div className="absolute w-16 h-16 rounded-full bg-violet-500/10 animate-ping" />
        <div className="absolute w-12 h-12 rounded-full bg-violet-500/15 animate-pulse" />
        <div className="relative w-10 h-10 rounded-xl bg-violet-600/30 border border-violet-500/40 flex items-center justify-center">
          <Wand2 className="h-5 w-5 text-violet-400" />
        </div>
      </div>

      <div className="text-center">
        <p className="text-sm font-semibold text-zinc-200 mb-0.5">Generating your review config</p>
        <p className="text-xs text-zinc-500">Usually 10-20 seconds -- sit tight</p>
      </div>

      {/* Step list */}
      <div className="w-full flex flex-col gap-1.5">
        {GEN_STEPS.map((step, i) => {
          const done = doneSteps.has(i)
          const active = activeStep === i
          const pending = !done && !active
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
              {/* Status indicator */}
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

              {/* Text */}
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
              </div>

              {/* Active dots animation */}
              {active && (
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
// AI Generate panel (shown before generation completes)
// ---------------------------------------------------------------------------

interface AIGeneratePanelProps {
  onGenerated: (yaml: string, question: string) => void
}

function AIGeneratePanel({ onGenerated }: AIGeneratePanelProps) {
  const [question, setQuestion] = useState("")
  const [geminiKey, setGeminiKey] = useState("")
  const [showKey, setShowKey] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const stored = loadApiKeys()
    if (stored?.gemini) setGeminiKey(stored.gemini)
  }, [])

  async function handleGenerate() {
    if (!question.trim()) return
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

  return (
    <div className="flex flex-col gap-3">
      <div className="text-center py-4">
        <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-violet-600/20 border border-violet-500/30 mb-3">
          <Wand2 className="h-5 w-5 text-violet-400" />
        </div>
        <h3 className="text-sm font-semibold text-zinc-200 mb-1">
          Describe your research question
        </h3>
        <p className="text-xs text-zinc-500 max-w-sm mx-auto leading-relaxed">
          We will automatically generate the PICO framework, search keywords, inclusion and
          exclusion criteria, and scope -- ready to launch.
        </p>
      </div>

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
      <p className="text-xs text-zinc-600 -mt-1">Cmd+Enter to generate</p>

      {/* Gemini API key */}
      <div>
        <label className="block text-xs font-medium text-zinc-400 mb-1">
          Gemini API Key <span className="text-red-500">*</span>
        </label>
        <div className="relative">
          <Input
            type={showKey ? "text" : "password"}
            value={geminiKey}
            onChange={(e) => setGeminiKey(e.target.value)}
            placeholder="AIza..."
            autoComplete="off"
            className="pr-9 h-9 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
        <p className="text-xs text-zinc-600 mt-1">
          Used only for config generation. You can set it again in API Keys before starting.
        </p>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
          <X className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          <span className="leading-relaxed">{error}</span>
        </div>
      )}

      <Button
        type="button"
        onClick={() => void handleGenerate()}
        disabled={!question.trim() || !geminiKey.trim()}
        className="w-full h-10 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-medium gap-2 transition-colors"
      >
        <Sparkles className="h-4 w-4" />
        Generate Review Config
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main SetupView
// ---------------------------------------------------------------------------

export function SetupView({ defaultReviewYaml, onSubmit, disabled }: SetupViewProps) {
  const [mode, setMode] = useState<Mode>("ai")
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadYaml, setLoadYaml] = useState<string | null>(null)
  const [loadedRunTopic, setLoadedRunTopic] = useState<string | null>(null)
  const [loadingConfig, setLoadingConfig] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)
  const [aiGeneratedQuestion, setAiGeneratedQuestion] = useState<string | null>(null)

  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchHistory().then(setHistory).catch(() => setHistory([]))
  }, [])

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    if (showDropdown) document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showDropdown])

  async function handleLoadRun(entry: HistoryEntry) {
    setShowDropdown(false)
    setLoadError(null)
    setLoadingConfig(entry.workflow_id)
    try {
      const yaml = await fetchRunConfig(entry.workflow_id)
      if (!yaml) {
        setLoadError(
          `Config not saved for "${entry.topic}". Only runs started after this feature was added can be loaded.`
        )
        return
      }
      setLoadYaml(yaml)
      setLoadedRunTopic(entry.topic)
      setAiGeneratedQuestion(null)
      setMode("manual")
    } catch {
      setLoadError("Failed to load config for that run.")
    } finally {
      setLoadingConfig(null)
    }
  }

  function clearLoaded() {
    setLoadYaml(null)
    setLoadedRunTopic(null)
    setLoadError(null)
    setAiGeneratedQuestion(null)
  }

  function handleModeChange(m: Mode) {
    setMode(m)
    setLoadError(null)
  }

  function handleAIGenerated(yaml: string, question: string) {
    setLoadYaml(yaml)
    setAiGeneratedQuestion(question)
  }

  const recentRuns = history.filter((h) => h.status === "completed").slice(0, 10)
  const allSectionsOpen = ["pico", "keywords", "criteria", "sources", "api-keys"]

  return (
    <div className="max-w-2xl mx-auto pt-2 pb-16">
      <div className="mb-5">
        <h2 className="text-base font-semibold text-zinc-200">New Systematic Review</h2>
        <p className="text-xs text-zinc-500 mt-1 leading-relaxed">
          Choose how you want to configure your review below.
        </p>
      </div>

      <ModeSelector mode={mode} onSelect={handleModeChange} />

      {/* Load from past run (available in all modes) */}
      {recentRuns.length > 0 && (
        <div className="relative mb-4" ref={dropdownRef}>
          <div className="flex items-center gap-2">
            {loadedRunTopic ? (
              <div className="flex items-center gap-2 text-xs text-violet-300 bg-violet-600/15 border border-violet-500/30 rounded-lg px-3 py-1.5">
                <RotateCcw className="h-3 w-3 flex-shrink-0" />
                <span className="truncate max-w-[280px]">
                  Loaded config from: &quot;{loadedRunTopic}&quot;
                </span>
                <button
                  type="button"
                  onClick={clearLoaded}
                  className="ml-1 text-violet-400 hover:text-violet-200 transition-colors flex-shrink-0"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowDropdown((v) => !v)}
                disabled={!!loadingConfig}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <RotateCcw className={`h-3.5 w-3.5 ${loadingConfig ? "animate-spin" : ""}`} />
                {loadingConfig ? "Loading config..." : "Load config from a past run"}
                <ChevronDown className={`h-3 w-3 transition-transform ${showDropdown ? "" : "-rotate-90"}`} />
              </button>
            )}
          </div>

          {showDropdown && (
            <div className="absolute left-0 top-full mt-1 z-20 w-[420px] max-h-[280px] overflow-y-auto bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl">
              <div className="px-3 py-2 border-b border-zinc-800">
                <p className="text-xs text-zinc-500">Select a completed run to reuse its configuration</p>
              </div>
              {recentRuns.map((entry) => (
                <button
                  key={entry.workflow_id}
                  type="button"
                  onClick={() => void handleLoadRun(entry)}
                  className="w-full flex items-start gap-2.5 px-3 py-2.5 hover:bg-zinc-800/60 transition-colors text-left border-b border-zinc-800/50 last:border-0"
                >
                  <Clock className="h-3.5 w-3.5 text-zinc-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-zinc-200 truncate leading-snug">{entry.topic}</p>
                    <p className="text-xs text-zinc-600 mt-0.5">{formatDate(entry.created_at)}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Load error */}
      {loadError && (
        <div className="mb-4 flex items-start gap-2 text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2.5">
          <span className="leading-relaxed">{loadError}</span>
          <button
            type="button"
            onClick={() => setLoadError(null)}
            className="ml-auto text-amber-500/60 hover:text-amber-400 transition-colors flex-shrink-0"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Mode 1: AI Generate */}
      {mode === "ai" && !aiGeneratedQuestion && (
        <AIGeneratePanel onGenerated={handleAIGenerated} />
      )}

      {mode === "ai" && aiGeneratedQuestion && (
        <>
          <div className="flex items-center gap-2.5 px-3 py-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl mb-4 text-xs text-emerald-400">
            <Sparkles className="h-3.5 w-3.5 flex-shrink-0" />
            <span className="flex-1 leading-relaxed">
              Config generated from your research question. Review and edit the fields below,
              then click Start.
            </span>
            <button
              type="button"
              onClick={() => {
                setAiGeneratedQuestion(null)
                setLoadYaml(null)
              }}
              className="text-emerald-600 hover:text-emerald-400 transition-colors flex-shrink-0"
              title="Generate again"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <RunForm
            defaultReviewYaml={defaultReviewYaml}
            onSubmit={onSubmit}
            disabled={disabled}
            loadYaml={loadYaml}
            defaultOpenSections={allSectionsOpen}
          />
        </>
      )}

      {/* Mode 2: YAML */}
      {mode === "yaml" && (
        <RunForm
          defaultReviewYaml={defaultReviewYaml}
          onSubmit={onSubmit}
          disabled={disabled}
          loadYaml={loadYaml}
          defaultOpenSections={[]}
          defaultAdvancedOpen={true}
        />
      )}

      {/* Mode 3: Manual */}
      {mode === "manual" && (
        <RunForm
          defaultReviewYaml={defaultReviewYaml}
          onSubmit={onSubmit}
          disabled={disabled}
          loadYaml={loadYaml}
          defaultOpenSections={allSectionsOpen}
        />
      )}
    </div>
  )
}
