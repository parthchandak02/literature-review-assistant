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
  FileCode2,
  HeartPulse,
  HelpCircle,
  Key,
  Upload,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { PageSection } from "@/components/ui/section"
import { YamlEditor } from "@/components/YamlEditor"
import {
  fetchEnvKeys,
  fetchEnvKeysStatus,
  fetchRequiredLlmUiKeys,
  fetchHistory,
  fetchRunConfig,
  buildRunRequest,
  emptyStoredApiKeys,
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
import type { EnvKeysStatus, HistoryEntry, RunRequest, StoredApiKeys } from "@/lib/api"

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
  deepseekKey: string
  csvFile?: File
  csvMode: CsvMode
  generationProfile: GenerationProfile
}

// ---------------------------------------------------------------------------
// Generation steps (driven by real SSE events from the backend)
// ---------------------------------------------------------------------------

// Stage 1 config research uses the configured LLM (DeepSeek by default); optional
// connector API keys are entered before launch in Stage 2.
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
              ? "bg-intent-warning-subtle border-intent-warning-border"
              : active
              ? "bg-intent-warning-subtle border-intent-warning-border"
              : "bg-surface-2/40 border-border"
            : fallbackSkipped
            ? "bg-intent-info-subtle border-intent-info-border"
            : done
            ? "bg-intent-success-subtle border-intent-success-border"
            : active
            ? "bg-intent-primary-subtle border-intent-primary-border"
            : "bg-surface-2/40 border-border"
          const titleCls = fallbackDegraded
            ? done || active
              ? "text-foreground"
              : "text-muted"
            : fallbackSkipped
            ? "text-foreground"
            : done
            ? "text-foreground"
            : active
            ? "text-foreground"
            : "text-muted"
          const detailCls = fallbackDegraded
            ? "text-muted"
            : fallbackSkipped
            ? "text-muted"
            : done
            ? "text-muted"
            : "text-muted"
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
  const [showDeepseek, setShowDeepseek] = useState(false)

  const fields: { id: keyof StoredApiKeys; label: string; placeholder: string; required?: boolean }[] = [
    { id: "deepseek", label: "DeepSeek API Key", placeholder: "sk-...", required: true },
    { id: "gemini", label: "Gemini API Key", placeholder: "optional -- AIza..." },
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
      {/* DeepSeek key -- always shown */}
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">
          {primaryField.label} <span className="text-intent-danger">*</span>
        </label>
        <div className="relative">
          <Input
            type={showDeepseek ? "text" : "password"}
            value={keys.deepseek}
            onChange={(e) => onChange({ ...keys, deepseek: e.target.value })}
            placeholder={primaryField.placeholder}
            autoComplete="off"
            className="pr-9 h-9 text-xs bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border"
          />
          <button
            type="button"
            onClick={() => setShowDeepseek((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-foreground transition-colors"
          >
            {showDeepseek ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Optional keys toggle */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
      >
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
        {expanded ? "Hide optional API keys" : "Add optional API keys (OpenAlex, PubMed, IEEE...)"}
      </button>

      {expanded && extraFields.map((f) => (
        <div key={f.id}>
          <label className="block text-xs font-medium text-muted mb-1">
            {f.label}
          </label>
          <Input
            type="text"
            value={keys[f.id] ?? ""}
            onChange={(e) => onChange({ ...keys, [f.id]: e.target.value })}
            placeholder={f.placeholder}
            autoComplete="off"
            className="h-9 text-xs bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary-border"
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
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Key className="h-3.5 w-3.5 text-muted shrink-0" />
        <span className="text-xs font-semibold text-foreground flex-1">API Keys</span>
        {!keys.deepseek && (
          <span className="text-xs text-intent-danger font-medium">At least one LLM key required</span>
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
  initialDeepseekKey: string
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

  const mergeTooltip = "Run connector search first, then merge your CSV rows. Duplicates are removed."
  const masterTooltip = "Skip connector search and use only the studies in your CSV."

  return (
    <TooltipProvider delayDuration={250}>
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <label className="text-xs font-semibold text-muted uppercase tracking-wide cursor-default">
            CSV Import <span className="text-muted">(optional)</span>
          </label>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="text-muted hover:text-intent-info transition-colors rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-intent-primary-border"
                aria-label="About optional CSV import"
              >
                <HelpCircle className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="top"
              align="start"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p className="font-semibold text-foreground mb-1">Optional CSV</p>
              <p>Add a Scopus-style spreadsheet to either enrich automated search or replace it with your fixed list.</p>
            </TooltipContent>
          </Tooltip>
        </div>

        <div
          className="inline-flex rounded-lg border border-border bg-surface-2/70 p-0.5 gap-0.5 mb-2"
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
                    ? "bg-intent-primary-subtle text-foreground shadow-sm ring-1 ring-intent-primary-border"
                    : "text-muted hover:text-foreground"
                }`}
              >
                Merge with search
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p>{mergeTooltip}</p>
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
                    ? "bg-intent-primary-subtle text-foreground shadow-sm ring-1 ring-intent-primary-border"
                    : "text-muted hover:text-foreground"
                }`}
              >
                Use as master list
              </button>
            </TooltipTrigger>
            <TooltipContent
              side="bottom"
              sideOffset={6}
              className="max-w-[260px] text-xs leading-relaxed px-3 py-2.5 bg-card border border-border text-foreground shadow-xl"
            >
              <p>{masterTooltip}</p>
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
              ? "border-intent-success/60 bg-intent-success-subtle"
              : "border-border bg-surface-2/50 hover:border-border hover:bg-surface-2"
          }`}
        >
          <Upload className="h-5 w-5 text-muted" />
          <p className="text-xs text-muted text-center leading-relaxed">
            Drop a CSV file here, or{" "}
            <span className="text-intent-success font-medium">click to browse</span>
          </p>
          <p className="text-xs text-muted">
            {mode === "masterlist"
              ? "Use your curated study list as the primary input."
              : "Scopus export format (Title, Authors, Year, DOI, Abstract...)."}
          </p>
        </div>
      ) : (
        /* File info row */
        <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
          analysis?.valid
            ? "border-intent-success-border bg-intent-success-subtle"
            : analysis && !analysis.valid
            ? "border-intent-warning-border bg-intent-warning-subtle"
            : "border-border bg-surface-2/50"
        }`}>
          <FileText className={`h-4 w-4 shrink-0 ${analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-muted"}`} />
          <div className="flex-1 min-w-0">
            <p className={`text-xs font-medium truncate ${analysis?.valid ? "text-intent-success" : analysis ? "text-intent-warning" : "text-foreground"}`}>
              {file.name}
            </p>
            <p className={`text-xs mt-0.5 ${analysis?.valid ? "text-intent-success/70" : "text-muted"}`}>
              {(file.size / 1024).toFixed(0)} KB
            </p>
          </div>
          <button
            type="button"
            onClick={() => { onFile(null); setAnalysis(null) }}
            className="text-muted hover:text-foreground transition-colors shrink-0"
            aria-label="Remove file"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Validation panel */}
      {file && (
        <div className="mt-2 rounded-xl border border-border bg-card/80 overflow-hidden">
          {analysing && (
            <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted">
              <Spinner size="sm" className="shrink-0" />
              Analysing CSV...
            </div>
          )}

          {analysis && !analysing && (
            <>
              {/* Status row */}
              <div className={`flex items-center gap-2.5 px-4 py-3 border-b border-border/60 ${analysis.valid ? "bg-intent-success-subtle" : "bg-intent-warning-subtle"}`}>
                {analysis.valid ? (
                  <CheckCircle2 className="h-4 w-4 text-intent-success shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-intent-warning shrink-0" />
                )}
                <div className="flex-1">
                  {analysis.error ? (
                    <p className="text-xs font-semibold text-intent-danger">{analysis.error}</p>
                  ) : analysis.valid ? (
                    <p className="text-xs font-semibold text-intent-success">
                      {analysis.rowCount.toLocaleString()} papers ready to screen
                    </p>
                  ) : analysis.missingRequired.length > 0 ? (
                    <p className="text-xs font-semibold text-intent-warning">
                      Missing required column: {analysis.missingRequired.join(", ")}
                    </p>
                  ) : (
                    <p className="text-xs font-semibold text-intent-warning">
                      {analysis.rowCount === 0 ? "No data rows found" : `${analysis.rowCount.toLocaleString()} rows found`}
                    </p>
                  )}
                  {analysis.valid && (
                    <p className="text-xs text-intent-success/70 mt-0.5">
                      {mode === "masterlist"
                        ? "This CSV will be used as the review master list instead of connector search."
                        : "Connector search will run, then this CSV will be merged before screening."}
                    </p>
                  )}
                </div>
              </div>

              {/* Column grid */}
              <div className="px-4 py-3">
                <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
                  Detected columns
                </p>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                  {[...CSV_REQUIRED_COLS, ...CSV_EXPECTED_COLS].map((col) => {
                    const present = analysis.headers.includes(col)
                    const required = CSV_REQUIRED_COLS.includes(col)
                    return (
                      <div key={col} className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          present ? "bg-intent-success" : required ? "bg-intent-danger" : "bg-surface-4"
                        }`} />
                        <span className={`text-xs truncate ${
                          present ? "text-foreground" : required ? "text-intent-danger" : "text-muted"
                        }`}>
                          {col}
                          {required && !present && " *"}
                        </span>
                      </div>
                    )
                  })}
                </div>
                {analysis.missingExpected.length > 0 && analysis.valid && (
                  <p className="text-xs text-muted mt-2 leading-relaxed">
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
  initialDeepseekKey,
  initialCsvFile,
  initialCsvMode,
}: Stage1Props) {
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
  const [pendingDeepseekKey, setPendingDeepseekKey] = useState("")
  const [pendingCsvFile, setPendingCsvFile] = useState<File | null>(null)
  const [pendingCsvMode, setPendingCsvMode] = useState<CsvMode>("supplementary")
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    fetchHistory()
      .then(setHistory)
      .catch((error) => {
        setHistory([])
        const message =
          error instanceof Error ? error.message : "Failed to load review history."
        setLoadError(message)
      })
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
          setPendingDeepseekKey(req.deepseekKey)
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
        initialDeepseekKey={pendingDeepseekKey}
        initialCsvFile={pendingCsvFile}
        initialCsvMode={pendingCsvMode}
      />
    </div>
  )
}
