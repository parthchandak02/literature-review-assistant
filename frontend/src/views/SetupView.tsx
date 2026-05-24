import { useState, useEffect, useRef } from "react"
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Clock,
  Eye,
  EyeOff,
  FileText,
  RotateCcw,
  Sparkles,
  Wand2,
  FileCode2,
  HeartPulse,
  HelpCircle,
  Key,
  Upload,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PageSection } from "@/components/ui/section"
import { YamlEditor } from "@/components/YamlEditor"
import {
  fetchEnvKeys,
  fetchRequiredLlmUiKeys,
  fetchHistory,
  fetchRunConfig,
  loadApiKeys,
  saveApiKeys,
} from "@/lib/api"
import { FetchError } from "@/components/ui/feedback"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { formatShortDate } from "@/lib/format"
import type { HistoryEntry, RunRequest, StoredApiKeys } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SetupViewProps {
  defaultReviewYaml: string
  onGenerateDraft: (req: ConfigGenerateRequest) => void
  onOpenDraftWithYaml: (yaml: string) => void
  disabled: boolean
}

type CsvMode = "supplementary" | "masterlist"
type GenerationProfile = "standard" | "health_sdg"
export interface ConfigGenerateRequest {
  question: string
  geminiKey: string
  csvFile?: File
  csvMode: CsvMode
  generationProfile: GenerationProfile
}

// ---------------------------------------------------------------------------
// Generation steps (driven by real SSE events from the backend)
// ---------------------------------------------------------------------------

// Stage 1 web research is powered by Gemini tools (WebSearchTool/WebFetchTool),
// not the optional connector API keys entered before launch.
const GEN_STEPS: { key: string; label: string; detail: string }[] = [
  { key: "start",            label: "Analyzing your research question", detail: "Understanding scope, domain, and intent" },
  { key: "web_research",     label: "Searching the web",                detail: "Discovering brand names, synonyms, and domain terminology" },
  { key: "web_research_fallback", label: "Web search unavailable",      detail: "Falling back to model knowledge for this generation" },
  { key: "web_research_done",label: "Processing search results",        detail: "Building research brief from web findings" },
  { key: "structuring",      label: "Generating PICO and criteria",     detail: "Keywords, inclusion/exclusion criteria, domain and scope" },
  { key: "topic_routing",    label: "Applying domain routing policy",   detail: "Selecting connector policy from confidence-scored topic signals" },
  { key: "finalizing",       label: "Finalizing your config",           detail: "Validating and serializing to YAML" },
]

const WEB_RESEARCH_FALLBACK_STEP = "web_research_fallback"
const WEB_RESEARCH_DONE_INDEX = GEN_STEPS.findIndex((s) => s.key === "web_research_done")

function buildTopicRoutingText(stepMetadata: Record<string, unknown>): string | null {
  const domain = typeof stepMetadata.domain === "string" ? stepMetadata.domain : null
  const confidence = typeof stepMetadata.confidence === "number" ? stepMetadata.confidence : null
  const policy = typeof stepMetadata.policy === "string" ? stepMetadata.policy : null
  if (!domain && !policy && confidence === null) return null
  const confidenceTxt = confidence === null ? "n/a" : confidence.toFixed(2)
  return `Domain=${domain ?? "unknown"}, confidence=${confidenceTxt}, policy=${policy ?? "unknown"}`
}

function getFallbackStepLabel(fallbackSkipped: boolean, fallbackDegraded: boolean): string {
  if (fallbackSkipped) return "Web research backup skipped"
  if (fallbackDegraded) return "Web search unavailable"
  return "Web research backup (standby)"
}

function GenerationProgressCard({
  activeStepKey,
  stepMetadata,
  usedWebFallback,
  fallbackReason,
}: {
  activeStepKey: string
  stepMetadata: Record<string, unknown>
  usedWebFallback: boolean
  fallbackReason: string | null
}) {
  const activeIdx = GEN_STEPS.findIndex((s) => s.key === activeStepKey)
  const activeStep = activeIdx === -1 ? 0 : activeIdx
  const hasPassedWebSearch = activeStep > WEB_RESEARCH_DONE_INDEX
  const routeDetail = buildTopicRoutingText(stepMetadata)

  return (
    <PageSection icon={Sparkles} title="Config Generation Summary" description="Live generation progress">
      <div className="space-y-1.5">
        {GEN_STEPS.map((step, i) => {
          const fallbackSkipped =
            step.key === WEB_RESEARCH_FALLBACK_STEP && !usedWebFallback && hasPassedWebSearch
          const fallbackDegraded =
            step.key === WEB_RESEARCH_FALLBACK_STEP && usedWebFallback && (i <= activeStep)
          const done = i < activeStep
          const active = i === activeStep
          const showDetail = active || done || fallbackSkipped
          const rowCls = fallbackDegraded
            ? done
              ? "bg-amber-500/10 border-amber-500/30"
              : active
              ? "bg-amber-500/12 border-amber-500/40"
              : "bg-zinc-900/40 border-zinc-800"
            : fallbackSkipped
            ? "bg-sky-500/8 border-sky-500/20"
            : done
            ? "bg-emerald-500/8 border-emerald-500/20"
            : active
            ? "bg-violet-500/10 border-violet-500/30"
            : "bg-zinc-900/40 border-zinc-800"
          const titleCls = fallbackDegraded
            ? done || active
              ? "text-amber-200"
              : "text-zinc-600"
            : fallbackSkipped
            ? "text-sky-200/80"
            : done
            ? "text-emerald-300/80"
            : active
            ? "text-violet-200"
            : "text-zinc-600"
          const detailCls = fallbackDegraded
            ? "text-amber-300/70"
            : fallbackSkipped
            ? "text-sky-300/60"
            : done
            ? "text-emerald-400/50"
            : "text-zinc-500"
          const detailText = fallbackSkipped
            ? "Skipped because web research succeeded."
            : fallbackDegraded && fallbackReason
            ? `Falling back to model knowledge: ${fallbackReason}`
            : step.key === "topic_routing" && routeDetail
            ? routeDetail
            : step.detail
          const titleText =
            step.key === WEB_RESEARCH_FALLBACK_STEP
              ? getFallbackStepLabel(fallbackSkipped, fallbackDegraded)
              : step.label

          return (
            <div key={step.key} className={`rounded-lg border px-2.5 py-2 ${rowCls}`}>
              <p className={`text-xs font-medium leading-snug ${titleCls}`}>{titleText}</p>
              {showDetail && (
                <p className={`text-[11px] mt-1 leading-snug ${detailCls}`}>{detailText}</p>
              )}
            </div>
          )
        })}
      </div>
    </PageSection>
  )
}

// ---------------------------------------------------------------------------
// API Keys section (inline, used in Stage 2 before launching)
// ---------------------------------------------------------------------------

interface ApiKeysProps {
  keys: StoredApiKeys
  onChange: (k: StoredApiKeys) => void
  /** When true, render only form content (no card wrapper); parent uses PageSection. */
  embedded?: boolean
}

function ApiKeysSection({ keys, onChange, embedded }: ApiKeysProps) {
  const [expanded, setExpanded] = useState(false)
  const [showGemini, setShowGemini] = useState(false)

  const fields: { id: keyof StoredApiKeys; label: string; placeholder: string; required?: boolean }[] = [
    { id: "gemini", label: "Gemini API Key", placeholder: "AIza...", required: true },
    { id: "deepseek", label: "DeepSeek API Key", placeholder: "optional -- sk-..." },
    { id: "openrouter", label: "OpenRouter API Key", placeholder: "optional -- sk-or-v1-..." },
    { id: "openai", label: "OpenAI API Key", placeholder: "optional -- sk-..." },
    { id: "anthropic", label: "Anthropic API Key", placeholder: "optional -- sk-ant-..." },
    { id: "groq", label: "Groq API Key", placeholder: "optional -- gsk_..." },
    { id: "mistral", label: "Mistral API Key", placeholder: "optional -- ..." },
    { id: "cohere", label: "Cohere API Key", placeholder: "optional -- ..." },
    { id: "scopus", label: "Scopus API Key", placeholder: "optional -- Elsevier Scopus search" },
    { id: "wos", label: "Web of Science API Key", placeholder: "optional -- Clarivate WoS Starter API" },
    { id: "openalex", label: "OpenAlex API Key", placeholder: "optional -- register free at openalex.org/sign-up" },
    { id: "pubmedEmail", label: "PubMed Email", placeholder: "user@example.com" },
    { id: "pubmedApiKey", label: "PubMed API Key", placeholder: "optional -- increases rate limits" },
    { id: "ieee", label: "IEEE Xplore API Key", placeholder: "optional" },
    { id: "perplexity", label: "Perplexity API Key", placeholder: "pplx-..." },
    { id: "semanticScholar", label: "Semantic Scholar API Key", placeholder: "optional" },
    { id: "crossrefEmail", label: "Crossref Email", placeholder: "user@example.com" },
  ]

  const primaryField = fields[0]
  const extraFields = fields.slice(1)

  const formContent = (
    <div className={embedded ? "space-y-3" : "px-4 py-4 space-y-3"}>
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
            value={keys[f.id] ?? ""}
            onChange={(e) => onChange({ ...keys, [f.id]: e.target.value })}
            placeholder={f.placeholder}
            autoComplete="off"
            className="h-9 text-xs bg-zinc-950 border-zinc-700 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
          />
        </div>
      ))}
    </div>
  )

  if (embedded) {
    return formContent
  }

  return (
    <div className="card-surface overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800">
        <Key className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
        <span className="text-xs font-semibold text-zinc-300 flex-1">API Keys</span>
        {!keys.gemini && (
          <span className="text-xs text-red-400 font-medium">At least one LLM key required</span>
        )}
      </div>
      {formContent}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Stage 1 -- Question input
// ---------------------------------------------------------------------------

interface Stage1Props {
  onGenerateRequested: (req: ConfigGenerateRequest) => void
  onPasteYaml: () => void
  history: HistoryEntry[]
  onLoadFromHistory: (entry: HistoryEntry) => void
  loadingHistoryId: string | null
  loadError: string | null
  onClearError: () => void
  initialQuestion: string
  initialGeminiKey: string
  initialCsvFile: File | null
  initialCsvMode: CsvMode
}

// ---------------------------------------------------------------------------
// CSV validation helpers
// ---------------------------------------------------------------------------

const CSV_REQUIRED_COLS = ["Title"]
const CSV_EXPECTED_COLS = ["Authors", "Year", "Source title", "DOI", "Abstract", "Link", "Author Keywords"]

interface CsvAnalysis {
  rowCount: number
  headers: string[]
  presentExpected: string[]
  missingExpected: string[]
  missingRequired: string[]
  valid: boolean
  error: string | null
}

function parseCsvHeaderRow(line: string): string[] {
  const cols: string[] = []
  let cur = ""
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      inQuotes = !inQuotes
    } else if (ch === "," && !inQuotes) {
      cols.push(cur.trim().replace(/^"|"$/g, ""))
      cur = ""
    } else {
      cur += ch
    }
  }
  cols.push(cur.trim().replace(/^"|"$/g, ""))
  return cols
}

function countCsvDataRows(text: string): number {
  // Walk the text respecting quoted fields so embedded newlines don't skew the count.
  let rows = 0
  let inQuotes = false
  let firstRow = true
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') {
      inQuotes = !inQuotes
    } else if (ch === "\n" && !inQuotes) {
      if (firstRow) {
        firstRow = false
      } else {
        // peek ahead: if the rest is only whitespace, don't count trailing blank line
        const rest = text.slice(i + 1).trimStart()
        if (rest.length > 0) rows++
      }
    }
  }
  // If file has no trailing newline, the last row isn't counted yet
  if (!firstRow && text.trimEnd().length > 0 && text[text.length - 1] !== "\n") rows++
  return rows
}

async function analyzeCsvFile(file: File): Promise<CsvAnalysis> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onerror = () =>
      resolve({ rowCount: 0, headers: [], presentExpected: [], missingExpected: CSV_EXPECTED_COLS, missingRequired: CSV_REQUIRED_COLS, valid: false, error: "Failed to read file" })
    reader.onload = (e) => {
      const text = (e.target?.result ?? "") as string
      if (!text) {
        resolve({ rowCount: 0, headers: [], presentExpected: [], missingExpected: CSV_EXPECTED_COLS, missingRequired: CSV_REQUIRED_COLS, valid: false, error: "File is empty" })
        return
      }
      const firstNl = text.indexOf("\n")
      const headerLine = firstNl === -1 ? text : text.slice(0, firstNl).replace(/\r$/, "")
      const headers = parseCsvHeaderRow(headerLine)
      const rowCount = countCsvDataRows(text)
      const missingRequired = CSV_REQUIRED_COLS.filter((c) => !headers.includes(c))
      const presentExpected = CSV_EXPECTED_COLS.filter((c) => headers.includes(c))
      const missingExpected = CSV_EXPECTED_COLS.filter((c) => !headers.includes(c))
      resolve({
        rowCount,
        headers,
        presentExpected,
        missingExpected,
        missingRequired,
        valid: missingRequired.length === 0 && rowCount > 0,
        error: null,
      })
    }
    reader.readAsText(file, "utf-8")
  })
}

// ---------------------------------------------------------------------------
// CSV drop zone with inline validation (optional supplementary upload)
// ---------------------------------------------------------------------------

interface CsvDropZoneProps {
  file: File | null
  onFile: (f: File | null) => void
  mode: CsvMode
  onModeChange: (mode: CsvMode) => void
}

function CsvDropZone({ file, onFile, mode, onModeChange }: CsvDropZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [analysis, setAnalysis] = useState<CsvAnalysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting derived state when file prop clears is intentional
    if (!file) { setAnalysis(null); return }
    setAnalysing(true)
    analyzeCsvFile(file).then((result) => {
      setAnalysis(result)
      setAnalysing(false)
    }).catch(() => setAnalysing(false))
  }, [file])

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped && dropped.name.endsWith(".csv")) onFile(dropped)
  }

  function handleAccept(f: File | undefined) {
    if (f) onFile(f)
  }

  const mergeTooltip = (
    <>
      <p className="font-semibold text-zinc-100 mb-1.5">Merge with search</p>
      <p className="text-zinc-300/90 mb-1.5">
        Connector search runs first (OpenAlex, PubMed, etc.). Rows from your CSV are combined with those hits before screening.
      </p>
      <p className="text-zinc-400">
        Example: you have 80 hand-picked Scopus exports and still want automated search to add newer papers—duplicates drop out when merged.
      </p>
    </>
  )

  const masterTooltip = (
    <>
      <p className="font-semibold text-zinc-100 mb-1.5">Use as master list</p>
      <p className="text-zinc-300/90 mb-1.5">
        Your CSV is the canonical study set; the workflow treats it as the primary input instead of expanding via connector search.
      </p>
      <p className="text-zinc-400">
        Example: you already locked a PRISMA table of 42 included studies and want screening and extraction on exactly those rows.
      </p>
    </>
  )

  return (
    <TooltipProvider delayDuration={250}>
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wide cursor-default">
            CSV Import <span className="text-zinc-600">(optional)</span>
          </label>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="text-zinc-600 hover:text-blue-400/90 transition-colors rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/40"
                aria-label="About optional CSV import"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              align="start"
              className="max-w-[280px] border-zinc-700 bg-zinc-950 text-xs text-zinc-300 leading-relaxed px-3 py-2.5 shadow-lg"
            >
              <p className="font-semibold text-zinc-100 mb-1">Optional CSV</p>
              <p>Add a Scopus-style spreadsheet to either enrich automated search or replace it with your fixed list.</p>
            </TooltipContent>
          </Tooltip>
        </div>

        <div
          className="inline-flex rounded-lg border border-zinc-700 bg-zinc-900/70 p-0.5 gap-0.5 mb-2"
          role="radiogroup"
          aria-label="How to use the CSV"
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={mode === "supplementary"}
                onClick={() => onModeChange("supplementary")}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors min-w-0 ${
                  mode === "supplementary"
                    ? "bg-violet-500/15 text-violet-200 shadow-sm ring-1 ring-violet-500/35"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                Merge with search
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              className="max-w-[280px] border-zinc-700 bg-zinc-950 text-xs leading-relaxed px-3 py-2.5 shadow-lg"
            >
              {mergeTooltip}
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                role="radio"
                aria-checked={mode === "masterlist"}
                onClick={() => onModeChange("masterlist")}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors min-w-0 ${
                  mode === "masterlist"
                    ? "bg-violet-500/15 text-violet-200 shadow-sm ring-1 ring-violet-500/35"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                Use as master list
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              className="max-w-[280px] border-zinc-700 bg-zinc-950 text-xs leading-relaxed px-3 py-2.5 shadow-lg"
            >
              {masterTooltip}
            </TooltipContent>
          </Tooltip>
        </div>

        {/* Drop zone / file picker */}
      {!file ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
            dragging
              ? "border-emerald-500/60 bg-emerald-500/8"
              : "border-zinc-700 bg-zinc-900/50 hover:border-zinc-600 hover:bg-zinc-900"
          }`}
        >
          <Upload className="h-5 w-5 text-zinc-500" />
          <p className="text-xs text-zinc-500 text-center leading-relaxed">
            Drop a CSV file here, or{" "}
            <span className="text-emerald-400 font-medium">click to browse</span>
          </p>
          <p className="text-xs text-zinc-600">
            {mode === "masterlist"
              ? "Use your curated study list as the primary input."
              : "Scopus export format (Title, Authors, Year, DOI, Abstract...)."}
          </p>
        </div>
      ) : (
        /* File info row */
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
          analysis?.valid
            ? "border-emerald-500/30 bg-emerald-500/8"
            : analysis && !analysis.valid
            ? "border-amber-500/30 bg-amber-500/8"
            : "border-zinc-700 bg-zinc-900/50"
        }`}>
          <FileText className={`h-4 w-4 shrink-0 ${analysis?.valid ? "text-emerald-400" : analysis ? "text-amber-400" : "text-zinc-500"}`} />
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-medium truncate ${analysis?.valid ? "text-emerald-300" : analysis ? "text-amber-300" : "text-zinc-300"}`}>
              {file.name}
            </p>
            <p className={`text-xs mt-0.5 ${analysis?.valid ? "text-emerald-500/70" : "text-zinc-600"}`}>
              {(file.size / 1024).toFixed(0)} KB
            </p>
          </div>
          <button
            type="button"
            onClick={() => { onFile(null); setAnalysis(null) }}
            className="text-zinc-500 hover:text-zinc-300 transition-colors shrink-0"
            aria-label="Remove file"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Validation panel */}
      {file && (
        <div className="mt-2 rounded-xl border border-zinc-800 bg-zinc-950/80 overflow-hidden">
          {analysing && (
            <div className="flex items-center gap-2 px-4 py-3 text-xs text-zinc-500">
              <div className="h-3 w-3 rounded-full border border-zinc-600 border-t-zinc-400 animate-spin shrink-0" />
              Analysing CSV...
            </div>
          )}

          {analysis && !analysing && (
            <>
              {/* Status row */}
              <div className={`flex items-center gap-2.5 px-4 py-3 border-b border-zinc-800/60 ${analysis.valid ? "bg-emerald-500/6" : "bg-amber-500/6"}`}>
                {analysis.valid ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
                )}
                <div className="flex-1">
                  {analysis.error ? (
                    <p className="text-xs font-semibold text-red-400">{analysis.error}</p>
                  ) : analysis.valid ? (
                    <p className="text-xs font-semibold text-emerald-300">
                      {analysis.rowCount.toLocaleString()} papers ready to screen
                    </p>
                  ) : analysis.missingRequired.length > 0 ? (
                    <p className="text-xs font-semibold text-amber-300">
                      Missing required column: {analysis.missingRequired.join(", ")}
                    </p>
                  ) : (
                    <p className="text-xs font-semibold text-amber-300">
                      {analysis.rowCount === 0 ? "No data rows found" : `${analysis.rowCount.toLocaleString()} rows found`}
                    </p>
                  )}
                  {analysis.valid && (
                    <p className="text-xs text-emerald-500/70 mt-0.5">
                      {mode === "masterlist"
                        ? "This CSV will be used as the review master list instead of connector search."
                        : "Connector search will run, then this CSV will be merged before screening."}
                    </p>
                  )}
                </div>
              </div>

              {/* Column grid */}
              <div className="px-4 py-3">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                  Detected columns
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                  {[...CSV_REQUIRED_COLS, ...CSV_EXPECTED_COLS].map((col) => {
                    const present = analysis.headers.includes(col)
                    const required = CSV_REQUIRED_COLS.includes(col)
                    return (
                      <div key={col} className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          present ? "bg-emerald-400" : required ? "bg-red-400" : "bg-zinc-700"
                        }`} />
                        <span className={`text-xs truncate ${
                          present ? "text-zinc-300" : required ? "text-red-400" : "text-zinc-600"
                        }`}>
                          {col}
                          {required && !present && " *"}
                        </span>
                      </div>
                    )
                  })}
                </div>
                {analysis.missingExpected.length > 0 && analysis.valid && (
                  <p className="text-xs text-zinc-600 mt-2 leading-relaxed">
                    {analysis.missingExpected.length} optional column{analysis.missingExpected.length > 1 ? "s" : ""} not found - those fields will be blank in the review.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => handleAccept(e.target.files?.[0])}
      />
      </div>
    </TooltipProvider>
  )
}

// ---------------------------------------------------------------------------
// Stage 1 -- Question input
// ---------------------------------------------------------------------------

function QuestionStage({
  onGenerateRequested,
  onPasteYaml,
  history,
  onLoadFromHistory,
  loadingHistoryId,
  loadError,
  onClearError,
  initialQuestion,
  initialGeminiKey,
  initialCsvFile,
  initialCsvMode,
}: Stage1Props) {
  const [question, setQuestion] = useState(initialQuestion)
  const [geminiKey, setGeminiKey] = useState(
    () => initialGeminiKey || (loadApiKeys()?.gemini ?? "")
  )

  // Backfill Gemini key from .env if not already in localStorage
  useEffect(() => {
    if (geminiKey) return
    fetchEnvKeys().then((env) => { if (env.gemini) setGeminiKey(env.gemini) })
  }, [geminiKey])
  const [showKey, setShowKey] = useState(false)
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
    if (!question.trim() || !geminiKey.trim()) return
    onGenerateRequested({
      question: question.trim(),
      geminiKey: geminiKey.trim(),
      csvFile: csvFile ?? undefined,
      csvMode,
      generationProfile,
    })
  }

  const completedRuns = history.filter((h) => h.status === "completed").slice(0, 10)
  const canGenerate = !!question.trim() && !!geminiKey.trim()

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

      <CsvDropZone file={csvFile} onFile={setCsvFile} mode={csvMode} onModeChange={setCsvMode} />

      {/* Research question */}
      <div>
        <label className="block label-caps font-semibold mb-2">
          Research Question
        </label>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={4}
          placeholder="e.g. What is the effect of [intervention] on [outcome] in [population]? Describe your research question in plain language."
          className="resize-none text-sm bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50 leading-relaxed"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void handleGenerate("standard")
          }}
        />
        <p className="text-xs text-zinc-600 mt-1.5">Cmd+Enter to generate</p>
      </div>

      {/* Gemini key */}
      <div>
        <label className="block label-caps font-semibold mb-2">
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

      {loadError && (
        <FetchError message={loadError} onRetry={onClearError} />
      )}

      {/* CTA */}
      <Button
        type="button"
        onClick={() => void handleGenerate()}
        disabled={!canGenerate}
        className="w-full h-11 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-semibold gap-2 transition-colors"
      >
        <Sparkles className="h-4 w-4" />
        Generate Review Config
      </Button>
      <Button
        type="button"
        onClick={() => void handleGenerate("health_sdg")}
        disabled={!canGenerate}
        className="w-full h-12 bg-emerald-600/90 hover:bg-emerald-500 disabled:opacity-40 text-white font-semibold gap-2.5 transition-colors border border-emerald-400/30"
      >
        <HeartPulse className="h-5 w-5" />
        Generate Health + SDG Config
      </Button>
      <p className="text-xs text-zinc-500 -mt-2 leading-relaxed">
        Hybrid framing mode: keeps your core topic while adding health-impact pathways and UN SDG alignment.
      </p>

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
            <div className="absolute left-0 top-full mt-1.5 z-20 w-[min(400px,calc(100vw-2rem))] max-h-[280px] overflow-y-auto glass-panel border border-zinc-700/80 rounded-xl shadow-xl">
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
}: Stage2Props) {
  const [keys, setKeys] = useState<StoredApiKeys>(() => {
    const defaults: StoredApiKeys = {
      gemini: "",
      deepseek: "",
      openrouter: "",
      openai: "",
      anthropic: "",
      groq: "",
      mistral: "",
      cohere: "",
      openalex: "",
      ieee: "",
      pubmedEmail: "",
      pubmedApiKey: "",
      perplexity: "",
      semanticScholar: "",
      crossrefEmail: "",
      wos: "",
      scopus: "",
    }
    const saved = loadApiKeys()
    // Merge saved keys with defaults so that newly-added fields get empty-string
    // values even when the persisted object predates them (avoids undefined ->
    // uncontrolled input problem in React).
    return saved ? { ...defaults, ...saved } : defaults
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [requiredLlmUiKeys, setRequiredLlmUiKeys] = useState<string[]>(["gemini"])

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
      const req: RunRequest = {
        review_yaml: yaml || defaultYaml,
        gemini_api_key: keys.gemini,
        deepseek_api_key: keys.deepseek || undefined,
        openrouter_api_key: keys.openrouter || undefined,
        openai_api_key: keys.openai || undefined,
        anthropic_api_key: keys.anthropic || undefined,
        groq_api_key: keys.groq || undefined,
        mistral_api_key: keys.mistral || undefined,
        cohere_api_key: keys.cohere || undefined,
        openalex_api_key: keys.openalex || undefined,
        ieee_api_key: keys.ieee || undefined,
        pubmed_email: keys.pubmedEmail || undefined,
        pubmed_api_key: keys.pubmedApiKey || undefined,
        perplexity_api_key: keys.perplexity || undefined,
        semantic_scholar_api_key: keys.semanticScholar || undefined,
        crossref_email: keys.crossrefEmail || undefined,
        wos_api_key: keys.wos || undefined,
        scopus_api_key: keys.scopus || undefined,
      }
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
            className="text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 shrink-0 -ml-2"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Back
          </Button>
          <span className="text-zinc-600">|</span>
          <span className="text-xs text-zinc-500">
            <span className="text-emerald-500/80 font-medium">1. Question</span>
            <span className="text-zinc-600 mx-1.5">/</span>
            <span className="text-violet-300 font-medium">2. Config</span>
          </span>
        </div>
        <div>
          <h2 className="text-base font-semibold text-zinc-100">Review Configuration</h2>
          {question && (
            <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed truncate max-w-xl" title={question}>
              Generated for: {question}
            </p>
          )}
        </div>
      </div>

      {csvFile && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 bg-blue-500/10 border border-blue-500/20 rounded-xl text-xs text-blue-300">
          <Upload className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
          <span className="leading-relaxed">
            {csvMode === "masterlist" ? "Master list CSV" : "Supplementary CSV"}:{" "}
            <span className="font-medium text-blue-200">{csvFile.name}</span>{" "}
            {csvMode === "masterlist"
              ? "will be used as the primary study list for this run."
              : "will be merged with connector search results before screening."}
          </span>
        </div>
      )}

      {/* Generated banner */}
      {question && (
        <div className="flex items-start gap-2.5 px-3 py-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-xs text-emerald-400">
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
        <ApiKeysSection keys={keys} onChange={setKeys} embedded />
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

export function SetupView({
  defaultReviewYaml,
  onGenerateDraft,
  onOpenDraftWithYaml,
  disabled,
}: SetupViewProps) {
  const [researchQuestion, setResearchQuestion] = useState<string>("")
  const [pendingGeminiKey, setPendingGeminiKey] = useState("")
  const [pendingCsvFile, setPendingCsvFile] = useState<File | null>(null)
  const [pendingCsvMode, setPendingCsvMode] = useState<CsvMode>("supplementary")
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    fetchHistory().then(setHistory).catch(() => setHistory([]))
  }, [])

  function handlePasteYaml() {
    onOpenDraftWithYaml(defaultReviewYaml)
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
      onOpenDraftWithYaml(yaml)
    } catch {
      setLoadError("Failed to load config for that run.")
    } finally {
      setLoadingHistoryId(null)
    }
  }

  return (
    <div className="max-w-xl mx-auto pt-6 pb-16 px-4" aria-disabled={disabled}>
      <QuestionStage
        onGenerateRequested={(req) => {
          setResearchQuestion(req.question)
          setPendingGeminiKey(req.geminiKey)
          setPendingCsvFile(req.csvFile ?? null)
          setPendingCsvMode(req.csvMode)
          onGenerateDraft(req)
        }}
        onPasteYaml={handlePasteYaml}
        history={history}
        onLoadFromHistory={(entry) => void handleLoadFromHistory(entry)}
        loadingHistoryId={loadingHistoryId}
        loadError={loadError}
        onClearError={() => setLoadError(null)}
        initialQuestion={researchQuestion}
        initialGeminiKey={pendingGeminiKey}
        initialCsvFile={pendingCsvFile}
        initialCsvMode={pendingCsvMode}
      />
    </div>
  )
}
