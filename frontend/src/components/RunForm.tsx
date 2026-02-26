import { useState, useEffect, useRef, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  ChevronDown,
  Eye,
  EyeOff,
  ExternalLink,
  FileKey,
  Loader,
  Play,
  Plus,
  X,
  Check,
  AlertCircle,
} from "lucide-react"
import { saveApiKeys, loadApiKeys, clearApiKeys } from "@/lib/api"
import type { RunRequest } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Pico {
  population: string
  intervention: string
  comparison: string
  outcome: string
}

interface ReviewConfig {
  research_question: string
  review_type: string
  pico: Pico
  keywords: string[]
  domain: string
  scope: string
  inclusion_criteria: string[]
  exclusion_criteria: string[]
  date_range_start: number
  date_range_end: number
  target_databases: string[]
}

export interface RunFormProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
  /** Pre-populate the form from a past run's YAML (e.g. "Reuse config"). */
  loadYaml?: string | null
  /** Section IDs to expand on first render. Pass [] to collapse all, or omit for default. */
  defaultOpenSections?: string[]
  /** When true, open the Advanced panel to the YAML tab on first render. */
  defaultAdvancedOpen?: boolean
}

// ---------------------------------------------------------------------------
// YAML builder -- produces valid YAML from ReviewConfig
// ---------------------------------------------------------------------------

function yamlStr(s: string): string {
  return '"' + s.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"'
}

function buildYaml(cfg: ReviewConfig): string {
  const lines: string[] = []
  lines.push(`research_question: ${yamlStr(cfg.research_question)}`)
  lines.push(`review_type: ${yamlStr(cfg.review_type)}`)
  lines.push("")
  lines.push("pico:")
  lines.push(`  population: ${yamlStr(cfg.pico.population)}`)
  lines.push(`  intervention: ${yamlStr(cfg.pico.intervention)}`)
  lines.push(`  comparison: ${yamlStr(cfg.pico.comparison)}`)
  lines.push(`  outcome: ${yamlStr(cfg.pico.outcome)}`)
  lines.push("")
  lines.push("keywords:")
  for (const kw of cfg.keywords) lines.push(`  - ${yamlStr(kw)}`)
  lines.push("")
  lines.push(`domain: ${yamlStr(cfg.domain)}`)
  lines.push(`scope: ${yamlStr(cfg.scope)}`)
  lines.push("")
  lines.push("inclusion_criteria:")
  for (const c of cfg.inclusion_criteria) lines.push(`  - ${yamlStr(c)}`)
  lines.push("")
  lines.push("exclusion_criteria:")
  for (const c of cfg.exclusion_criteria) lines.push(`  - ${yamlStr(c)}`)
  lines.push("")
  lines.push(`date_range_start: ${cfg.date_range_start}`)
  lines.push(`date_range_end: ${cfg.date_range_end}`)
  lines.push("")
  lines.push("target_databases:")
  for (const db of cfg.target_databases) lines.push(`  - ${db}`)
  lines.push("")
  lines.push("target_sections:")
  for (const s of ["abstract", "introduction", "methods", "results", "discussion", "conclusion"]) {
    lines.push(`  - ${s}`)
  }
  return lines.join("\n")
}

// ---------------------------------------------------------------------------
// YAML parser -- extracts ReviewConfig fields from a YAML string
// ---------------------------------------------------------------------------

function extractValue(raw: string): string {
  const t = raw.trim()
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, "\\")
  }
  return t
}

const LIST_FIELDS = new Set([
  "keywords",
  "inclusion_criteria",
  "exclusion_criteria",
  "target_databases",
  "target_sections",
])

const SKIP_BLOCKS = new Set(["protocol", "funding", "search_overrides", "api_keys"])

function parseYaml(yaml: string): Partial<ReviewConfig> {
  const lines = yaml.split("\n")
  const cfg: Partial<ReviewConfig> = {}
  let i = 0

  while (i < lines.length) {
    const raw = lines[i]
    const trimmed = raw.trim()

    if (!trimmed || trimmed.startsWith("#")) {
      i++
      continue
    }

    // pico: nested section
    if (trimmed === "pico:") {
      const pico: Pico = { population: "", intervention: "", comparison: "", outcome: "" }
      i++
      while (i < lines.length && lines[i].startsWith("  ")) {
        const m = lines[i].match(/^\s+(\w+):\s*(.*)$/)
        if (m && m[1] in pico) {
          ;(pico as unknown as Record<string, string>)[m[1]] = extractValue(m[2])
        }
        i++
      }
      cfg.pico = pico
      continue
    }

    // List fields
    const listMatch = trimmed.match(/^(\w+):$/)
    if (listMatch && LIST_FIELDS.has(listMatch[1])) {
      const key = listMatch[1] as keyof ReviewConfig
      const items: string[] = []
      i++
      while (i < lines.length && lines[i].trim().startsWith("- ")) {
        items.push(extractValue(lines[i].trim().slice(2).trim()))
        i++
      }
      ;(cfg as Record<string, unknown>)[key] = items
      continue
    }

    // Blocks we don't expose in the form -- skip
    if (listMatch && SKIP_BLOCKS.has(listMatch[1])) {
      i++
      while (i < lines.length && (lines[i].startsWith("  ") || lines[i].trim().startsWith("#"))) {
        i++
      }
      continue
    }

    // conflicts_of_interest: value (inline, no nested block)
    const kvMatch = trimmed.match(/^(\w+):\s*(.*)$/)
    if (kvMatch) {
      const [, key, rawVal] = kvMatch
      if (SKIP_BLOCKS.has(key) || key === "conflicts_of_interest") {
        i++
        continue
      }
      const val = extractValue(rawVal)
      if (key === "date_range_start" || key === "date_range_end") {
        ;(cfg as Record<string, unknown>)[key] = parseInt(val, 10) || 0
      } else {
        ;(cfg as Record<string, unknown>)[key] = val
      }
    }

    i++
  }

  return cfg
}

// ---------------------------------------------------------------------------
// Defaults and constants
// ---------------------------------------------------------------------------

const CURRENT_YEAR = new Date().getFullYear()

const EMPTY_CONFIG: ReviewConfig = {
  research_question: "",
  review_type: "systematic",
  pico: { population: "", intervention: "", comparison: "", outcome: "" },
  keywords: [],
  domain: "",
  scope: "",
  inclusion_criteria: [],
  exclusion_criteria: [],
  date_range_start: 2015,
  date_range_end: CURRENT_YEAR,
  target_databases: [
    "openalex",
    "pubmed",
    "arxiv",
    "ieee_xplore",
    "semantic_scholar",
    "crossref",
    "perplexity_search",
  ],
}

const DB_OPTIONS = [
  { id: "openalex", label: "OpenAlex" },
  { id: "pubmed", label: "PubMed" },
  { id: "arxiv", label: "arXiv" },
  { id: "ieee_xplore", label: "IEEE Xplore" },
  { id: "semantic_scholar", label: "Semantic Scholar" },
  { id: "crossref", label: "Crossref" },
  { id: "perplexity_search", label: "Perplexity" },
]

// Maps each database id to the credential keys it requires / benefits from.
// arXiv needs no credentials at all.
const DB_KEY_MAP: Record<string, string[]> = {
  openalex: ["openalex"],
  pubmed: ["pubmedEmail", "pubmedApiKey"],
  arxiv: [],
  ieee_xplore: ["ieee"],
  semantic_scholar: ["semanticScholar"],
  crossref: ["crossrefEmail"],
  perplexity_search: ["perplexity"],
}

interface CredMeta {
  key: string
  label: string
  required: boolean
  placeholder: string
  isEmail?: boolean
  note?: string
  link?: { label: string; href: string }
}

const CRED_META: CredMeta[] = [
  {
    key: "gemini",
    label: "Gemini API Key",
    required: true,
    placeholder: "AIza...",
    link: { label: "Google AI Studio", href: "https://aistudio.google.com/app/apikey" },
  },
  {
    key: "openalex",
    label: "OpenAlex API Key",
    required: false,
    placeholder: "optional -- increases rate limits",
    link: { label: "OpenAlex docs", href: "https://docs.openalex.org/how-to-use-the-api/api-overview" },
  },
  {
    key: "pubmedEmail",
    label: "PubMed Contact Email",
    required: true,
    placeholder: "you@example.com",
    isEmail: true,
    note: "Any valid email -- required by NCBI for API access.",
  },
  {
    key: "pubmedApiKey",
    label: "PubMed / NCBI API Key",
    required: false,
    placeholder: "optional -- 10x rate limit",
    link: { label: "NCBI account", href: "https://www.ncbi.nlm.nih.gov/account/" },
  },
  {
    key: "ieee",
    label: "IEEE Xplore API Key",
    required: false,
    placeholder: "optional",
    link: { label: "IEEE developer portal", href: "https://developer.ieee.org/" },
  },
  {
    key: "perplexity",
    label: "Perplexity API Key",
    required: true,
    placeholder: "pplx-...",
    link: { label: "Perplexity settings", href: "https://www.perplexity.ai/settings/api" },
  },
  {
    key: "semanticScholar",
    label: "Semantic Scholar API Key",
    required: false,
    placeholder: "optional",
    link: { label: "S2 API portal", href: "https://www.semanticscholar.org/product/api" },
  },
  {
    key: "crossrefEmail",
    label: "Crossref Polite Pool Email",
    required: false,
    placeholder: "you@example.com",
    isEmail: true,
    note: "Any valid email -- enables the polite pool for higher rate limits.",
  },
]

interface ApiKeyState {
  gemini: string
  openalex: string
  pubmedEmail: string
  pubmedApiKey: string
  ieee: string
  perplexity: string
  semanticScholar: string
  crossrefEmail: string
}

// ---------------------------------------------------------------------------
// Module-level maps and helpers for .env and YAML key import
// ---------------------------------------------------------------------------

// Maps .env variable names -> internal ApiKeyState keys
const ENV_VAR_MAP: Record<string, keyof ApiKeyState> = {
  GEMINI_API_KEY: "gemini",
  OPENALEX_API_KEY: "openalex",
  IEEE_API_KEY: "ieee",
  PUBMED_EMAIL: "pubmedEmail",
  NCBI_EMAIL: "pubmedEmail",
  PUBMED_API_KEY: "pubmedApiKey",
  PERPLEXITY_SEARCH_API_KEY: "perplexity",
  SEMANTIC_SCHOLAR_API_KEY: "semanticScholar",
  CROSSREF_EMAIL: "crossrefEmail",
}

// Maps YAML api_keys sub-key names -> internal ApiKeyState keys
const YAML_KEY_MAP: Record<string, keyof ApiKeyState> = {
  gemini: "gemini",
  openalex: "openalex",
  ieee: "ieee",
  pubmed_email: "pubmedEmail",
  pubmed_api_key: "pubmedApiKey",
  perplexity: "perplexity",
  semantic_scholar: "semanticScholar",
  crossref_email: "crossrefEmail",
}

/** Parse a .env-format string and return recognised key values. */
function parseEnvFile(raw: string): Partial<Record<keyof ApiKeyState, string>> {
  const parsed: Partial<Record<keyof ApiKeyState, string>> = {}
  for (const line of raw.split("\n")) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith("#")) continue
    const eqIdx = trimmed.indexOf("=")
    if (eqIdx === -1) continue
    const envKey = trimmed.slice(0, eqIdx).trim()
    let val = trimmed.slice(eqIdx + 1).trim()
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1)
    }
    const internalKey = ENV_VAR_MAP[envKey]
    if (internalKey && val) parsed[internalKey] = val
  }
  return parsed
}

/** Split .env lines into known (recognised) and unknown variable names. */
function classifyEnvLines(raw: string): { known: string[]; unknown: string[] } {
  const known: string[] = []
  const unknown: string[] = []
  for (const line of raw.split("\n")) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith("#")) continue
    const eqIdx = trimmed.indexOf("=")
    if (eqIdx === -1) continue
    const envKey = trimmed.slice(0, eqIdx).trim()
    if (ENV_VAR_MAP[envKey]) known.push(envKey)
    else unknown.push(envKey)
  }
  return { known, unknown }
}

/** Extract any api_keys: block from YAML and return found key values. */
function extractApiKeysFromYaml(yaml: string): Partial<Record<keyof ApiKeyState, string>> {
  const result: Partial<Record<keyof ApiKeyState, string>> = {}
  const lines = yaml.split("\n")
  let inApiKeys = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === "api_keys:") {
      inApiKeys = true
      continue
    }
    if (inApiKeys) {
      // Any non-blank top-level line (no leading whitespace) ends the block
      if (line.length > 0 && !line.startsWith(" ") && !line.startsWith("\t") && !trimmed.startsWith("#")) {
        break
      }
      const m = line.match(/^\s+(\w+):\s*(.+)$/)
      if (m) {
        const yamlKey = m[1]
        let val = m[2].trim()
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
          val = val.slice(1, -1)
        }
        const internalKey = YAML_KEY_MAP[yamlKey]
        if (internalKey && val) result[internalKey] = val
      }
    }
  }
  return result
}

/** Remove the api_keys: block from YAML before saving or submitting. */
function stripApiKeysFromYaml(yaml: string): string {
  const lines = yaml.split("\n")
  const out: string[] = []
  let skipping = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === "api_keys:") {
      skipping = true
      continue
    }
    if (skipping) {
      if (line.length > 0 && !line.startsWith(" ") && !line.startsWith("\t") && !trimmed.startsWith("#")) {
        skipping = false
        out.push(line)
      }
      continue
    }
    out.push(line)
  }
  return out.join("\n").trimEnd()
}

const PICO_FIELDS: Array<{ key: keyof Pico; label: string; placeholder: string }> = [
  { key: "population", label: "Population", placeholder: "e.g. Health science students" },
  { key: "intervention", label: "Intervention", placeholder: "e.g. Conversational AI tutors" },
  { key: "comparison", label: "Comparison", placeholder: "e.g. Traditional instruction" },
  { key: "outcome", label: "Outcome", placeholder: "e.g. Learning outcomes, engagement" },
]

// ---------------------------------------------------------------------------
// Accordion section component
// ---------------------------------------------------------------------------

interface SectionProps {
  id: string
  title: string
  open: boolean
  onToggle: () => void
  children: React.ReactNode
  badge?: string | number
  required?: boolean
  description?: string
}

function Section({ id: _id, title, open, onToggle, children, badge, required, description }: SectionProps) {
  return (
    <div className="border border-zinc-800 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 px-4 py-3 bg-zinc-900 hover:bg-zinc-800/60 transition-colors text-left"
      >
        <ChevronDown
          className={`h-4 w-4 text-zinc-500 transition-transform duration-200 flex-shrink-0 ${
            open ? "" : "-rotate-90"
          }`}
        />
        <span className="text-sm font-medium text-zinc-200 flex-1">
          {title}
          {required && <span className="text-red-500 ml-1">*</span>}
        </span>
        {badge !== undefined && (
          <span className="text-xs bg-zinc-700 text-zinc-300 px-2 py-0.5 rounded-full">
            {badge}
          </span>
        )}
      </button>
      {open && (
        <div className="px-4 pt-3 pb-4 bg-zinc-950 border-t border-zinc-800">
          {description && (
            <p className="text-xs text-zinc-500 mb-3 leading-relaxed">{description}</p>
          )}
          {children}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tag input for keywords
// ---------------------------------------------------------------------------

interface TagInputProps {
  tags: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
  disabled?: boolean
}

function TagInput({ tags, onChange, placeholder = "Type keyword and press Enter", disabled }: TagInputProps) {
  const [input, setInput] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  function addTags(raw: string) {
    const values = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
    const next = [...tags]
    for (const v of values) {
      if (!next.includes(v)) next.push(v)
    }
    onChange(next)
    setInput("")
  }

  function handleKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      if (input.trim()) addTags(input)
    } else if (e.key === "Backspace" && !input && tags.length > 0) {
      onChange(tags.slice(0, -1))
    }
  }

  return (
    <div
      className="flex flex-wrap gap-1.5 min-h-[42px] p-2 border border-zinc-800 rounded-lg bg-zinc-900 cursor-text"
      onClick={() => inputRef.current?.focus()}
    >
      {tags.map((tag) => (
        <span
          key={tag}
          className="flex items-center gap-1 text-xs bg-zinc-700/70 text-zinc-200 px-2 py-1 rounded-md"
        >
          {tag}
          {!disabled && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onChange(tags.filter((t) => t !== tag))
              }}
              className="text-zinc-400 hover:text-zinc-100 transition-colors"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      ))}
      <input
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKey}
        onBlur={() => {
          if (input.trim()) addTags(input)
        }}
        placeholder={tags.length === 0 ? placeholder : ""}
        disabled={disabled}
        className="flex-1 min-w-[140px] bg-transparent text-xs text-zinc-200 placeholder:text-zinc-600 outline-none"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Criteria list (inclusion / exclusion)
// ---------------------------------------------------------------------------

interface CriteriaListProps {
  items: string[]
  onChange: (items: string[]) => void
  placeholder: string
  color: "green" | "red"
  disabled?: boolean
}

function CriteriaList({ items, onChange, placeholder, color, disabled }: CriteriaListProps) {
  const borderClass = color === "green" ? "border-green-700/50" : "border-red-700/50"
  const addBtnClass =
    color === "green"
      ? "text-green-500/60 hover:text-green-400"
      : "text-red-500/60 hover:text-red-400"

  function update(index: number, value: string) {
    const next = [...items]
    next[index] = value
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item, idx) => (
        <div key={idx} className={`flex items-center gap-2 border-l-2 pl-2.5 ${borderClass}`}>
          <Input
            value={item}
            onChange={(e) => update(idx, e.target.value)}
            placeholder={placeholder}
            disabled={disabled}
            className="flex-1 h-8 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
          />
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(items.filter((_, i) => i !== idx))}
              className="text-zinc-600 hover:text-zinc-300 transition-colors flex-shrink-0"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <button
          type="button"
          onClick={() => onChange([...items, ""])}
          className={`flex items-center gap-1 text-xs mt-0.5 transition-colors ${addBtnClass}`}
        >
          <Plus className="h-3.5 w-3.5" />
          Add criterion
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Single credential field row
// ---------------------------------------------------------------------------

interface CredentialFieldProps {
  cred: CredMeta
  value: string
  onChange: (v: string) => void
  showKeys: boolean
  disabled: boolean
  saved: boolean
}

function CredentialField({ cred, value, onChange, showKeys, disabled, saved }: CredentialFieldProps) {
  const isEmailField = cred.isEmail
  return (
    <div>
      <div className="flex items-center justify-between mb-1 gap-2 flex-wrap">
        <label className="text-xs font-medium text-zinc-400">
          {cred.label}{" "}
          {cred.required ? (
            <span className="text-red-500">*</span>
          ) : (
            <span className="text-zinc-600 font-normal">(optional)</span>
          )}
        </label>
        <div className="flex items-center gap-2">
          {saved && (
            <span className="text-xs text-green-500/70 flex items-center gap-1">
              <Check className="h-3 w-3" />
              Saved
            </span>
          )}
          {cred.link && (
            <a
              href={cred.link.href}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-0.5 text-xs text-violet-400/70 hover:text-violet-300 transition-colors"
            >
              {cred.link.label}
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
          )}
        </div>
      </div>
      <Input
        type={isEmailField ? "email" : showKeys ? "text" : "password"}
        placeholder={cred.placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        autoComplete="off"
        className="bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-700 focus-visible:ring-violet-500/50 h-8 text-xs"
      />
      {cred.note && (
        <p className="text-xs text-zinc-600 mt-1 leading-relaxed">{cred.note}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Live summary bar
// ---------------------------------------------------------------------------

function buildSummary(cfg: ReviewConfig): string {
  const dbCount = cfg.target_databases.length
  const yearRange = `${cfg.date_range_start}-${cfg.date_range_end}`
  const q = cfg.research_question.trim()
  if (!q) return "Fill in a research question below to get started."
  const preview = q.length > 72 ? q.slice(0, 72) + "..." : q
  return `Search ${dbCount} database${dbCount !== 1 ? "s" : ""} (${yearRange}) for: "${preview}"`
}

// ---------------------------------------------------------------------------
// Main RunForm component
// ---------------------------------------------------------------------------

export function RunForm({ defaultReviewYaml, onSubmit, disabled, loadYaml, defaultOpenSections, defaultAdvancedOpen }: RunFormProps) {
  const [cfg, setCfg] = useState<ReviewConfig>(EMPTY_CONFIG)
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => defaultOpenSections !== undefined
      ? new Set(defaultOpenSections)
      : new Set(["pico", "keywords", "criteria", "sources", "api-keys"])
  )

  // Unified Advanced panel (YAML + .env, two inner tabs)
  const [advancedOpen, setAdvancedOpen] = useState(() => defaultAdvancedOpen ?? false)
  const [advancedTab, setAdvancedTab] = useState<"yaml" | "env">("yaml")
  const [yamlText, setYamlText] = useState("")
  const [yamlDirty, setYamlDirty] = useState(false)
  const [yamlKeyResult, setYamlKeyResult] = useState<{ applied: string[] } | null>(null)

  // .env tab inside Advanced panel
  const [envText, setEnvText] = useState("")
  const [envResult, setEnvResult] = useState<{ applied: string[]; unknown: string[] } | null>(null)

  // API keys -- unified state object
  const [keys, setKeys] = useState<ApiKeyState>({
    gemini: "",
    openalex: "",
    pubmedEmail: "",
    pubmedApiKey: "",
    ieee: "",
    perplexity: "",
    semanticScholar: "",
    crossrefEmail: "",
  })
  const [showKeys, setShowKeys] = useState(false)
  const [keysSaved, setKeysSaved] = useState(false)

  function setKey(k: keyof ApiKeyState, v: string) {
    setKeys((prev) => ({ ...prev, [k]: v }))
  }

  // Bulk keyword import
  const [kwBulk, setKwBulk] = useState("")
  const [showBulkKw, setShowBulkKw] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load API keys from localStorage on mount
  useEffect(() => {
    const stored = loadApiKeys()
    if (stored) {
      setKeys({
        gemini: stored.gemini || "",
        openalex: stored.openalex || "",
        pubmedEmail: stored.pubmedEmail || "",
        pubmedApiKey: stored.pubmedApiKey || "",
        ieee: stored.ieee || "",
        perplexity: stored.perplexity || "",
        semanticScholar: stored.semanticScholar || "",
        crossrefEmail: stored.crossrefEmail || "",
      })
      const anyKey = Object.values(stored).some(Boolean)
      setKeysSaved(anyKey)
    }
  }, [])

  // Seed form from the backend's default review.yaml (once, only if form is blank)
  useEffect(() => {
    if (!defaultReviewYaml) return
    setCfg((prev) => {
      if (prev.research_question) return prev // user already typed -- don't overwrite
      return { ...EMPTY_CONFIG, ...parseYaml(defaultReviewYaml) }
    })
  }, [defaultReviewYaml])

  // Override form from a past run's YAML whenever loadYaml prop changes
  useEffect(() => {
    if (!loadYaml) return
    const parsed = parseYaml(loadYaml)
    setCfg({ ...EMPTY_CONFIG, ...parsed })
    setYamlDirty(false)
  }, [loadYaml])

  // Keep YAML text in sync with form state (unless user is manually editing YAML)
  useEffect(() => {
    if (!yamlDirty) {
      setYamlText(buildYaml(cfg))
    }
  }, [cfg, yamlDirty])

  function toggle(id: string) {
    setOpenSections((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function updateCfg(patch: Partial<ReviewConfig>) {
    setYamlDirty(false) // form edit wins; re-sync YAML on next render
    setCfg((prev) => ({ ...prev, ...patch }))
  }

  function updatePico(patch: Partial<Pico>) {
    setYamlDirty(false)
    setCfg((prev) => ({ ...prev, pico: { ...prev.pico, ...patch } }))
  }

  function handleYamlChange(text: string) {
    setYamlText(text)
    setYamlDirty(true)
    // Parse review config fields and push to form state immediately
    const parsed = parseYaml(text)
    setCfg((prev) => ({ ...prev, ...parsed }))
    // Extract and apply any api_keys: block embedded in the YAML
    const detectedKeys = extractApiKeysFromYaml(text)
    const detectedEntries = Object.entries(detectedKeys) as [keyof ApiKeyState, string][]
    if (detectedEntries.length > 0) {
      const applied: string[] = detectedEntries.filter(([, v]) => v).map(([k]) => k)
      setKeys((prev) => {
        const next = { ...prev }
        for (const [k, v] of detectedEntries) if (v) next[k] = v
        return next
      })
      setYamlKeyResult({ applied })
      setKeysSaved(false)
      setOpenSections((prev) => new Set([...prev, "api-keys"]))
    } else {
      setYamlKeyResult(null)
    }
  }

  function handleYamlReset() {
    const fresh = buildYaml(cfg)
    setYamlText(fresh)
    setYamlDirty(false)
  }

  function toggleDb(id: string) {
    const dbs = cfg.target_databases.includes(id)
      ? cfg.target_databases.filter((d) => d !== id)
      : [...cfg.target_databases, id]
    updateCfg({ target_databases: dbs })
  }

  function clearKeys() {
    clearApiKeys()
    setKeys({
      gemini: "",
      openalex: "",
      pubmedEmail: "",
      pubmedApiKey: "",
      ieee: "",
      perplexity: "",
      semanticScholar: "",
      crossrefEmail: "",
    })
    setKeysSaved(false)
  }

  /** Apply keys parsed from a raw text string (used by both paste and Apply button). */
  function applyFromEnvText(raw: string) {
    if (!raw.trim()) return
    const parsed = parseEnvFile(raw)
    const { unknown } = classifyEnvLines(raw)
    if (Object.keys(parsed).length === 0) {
      setEnvResult({ applied: [], unknown })
      return
    }
    const applied: string[] = []
    setKeys((prev) => {
      const next = { ...prev }
      for (const [k, v] of Object.entries(parsed) as [keyof ApiKeyState, string][]) {
        if (v) { next[k] = v; applied.push(k) }
      }
      return next
    })
    setKeysSaved(false)
    setEnvResult({ applied, unknown })
    setOpenSections((prev) => new Set([...prev, "api-keys"]))
  }

  function clearEnv() {
    setEnvText("")
    setEnvResult(null)
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!cfg.research_question.trim()) {
      setError("Research question is required.")
      return
    }
    if (!keys.gemini.trim()) {
      setError("Gemini API key is required.")
      setOpenSections((prev) => new Set([...prev, "api-keys"]))
      return
    }
    // Warn if PubMed is selected but email is missing (it's required by NCBI)
    if (cfg.target_databases.includes("pubmed") && !keys.pubmedEmail.trim()) {
      setError("PubMed contact email is required when PubMed is selected.")
      setOpenSections((prev) => new Set([...prev, "api-keys"]))
      return
    }
    setError(null)
    setLoading(true)

    // Persist API keys to localStorage
    saveApiKeys({
      gemini: keys.gemini,
      openalex: keys.openalex,
      ieee: keys.ieee,
      pubmedEmail: keys.pubmedEmail,
      pubmedApiKey: keys.pubmedApiKey,
      perplexity: keys.perplexity,
      semanticScholar: keys.semanticScholar,
      crossrefEmail: keys.crossrefEmail,
    })
    setKeysSaved(true)

    const rawYaml = yamlDirty ? yamlText : buildYaml(cfg)
    const yaml = stripApiKeysFromYaml(rawYaml)
    try {
      await onSubmit({
        review_yaml: yaml,
        gemini_api_key: keys.gemini.trim(),
        openalex_api_key: keys.openalex.trim() || undefined,
        ieee_api_key: keys.ieee.trim() || undefined,
        pubmed_email: keys.pubmedEmail.trim() || undefined,
        pubmed_api_key: keys.pubmedApiKey.trim() || undefined,
        perplexity_api_key: keys.perplexity.trim() || undefined,
        semantic_scholar_api_key: keys.semanticScholar.trim() || undefined,
        crossref_email: keys.crossrefEmail.trim() || undefined,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const isValid = cfg.research_question.trim() !== "" && keys.gemini.trim() !== ""
  const summary = buildSummary(cfg)
  const critCount = cfg.inclusion_criteria.length + cfg.exclusion_criteria.length
  const advancedKeyCount =
    (yamlKeyResult?.applied.length ?? 0) + (envResult?.applied.length ?? 0)
  const advancedBadge = advancedKeyCount > 0 ? `${advancedKeyCount} keys applied` : undefined

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      {/* ----------------------------------------------------------------- */}
      {/* Live summary bar                                                   */}
      {/* ----------------------------------------------------------------- */}
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-xl px-4 py-2.5 mb-1">
        <p className="text-xs text-zinc-400 leading-relaxed">{summary}</p>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 1: Research Question (always visible, no toggle)           */}
      {/* ----------------------------------------------------------------- */}
      <div className="border border-zinc-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 bg-zinc-900">
          <span className="text-sm font-medium text-zinc-200">
            Research Question <span className="text-red-500">*</span>
          </span>
          <span className="text-xs text-zinc-600 tabular-nums">
            {cfg.research_question.length} chars
          </span>
        </div>
        <div className="px-4 pt-3 pb-4 bg-zinc-950 border-t border-zinc-800">
          <Textarea
            value={cfg.research_question}
            onChange={(e) => updateCfg({ research_question: e.target.value })}
            placeholder="e.g. How do conversational AI tutors impact learning outcomes, engagement, and knowledge retention in health science education?"
            disabled={disabled || loading}
            rows={3}
            className="resize-none text-sm bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50 leading-relaxed"
          />
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 2: PICO Framework                                          */}
      {/* ----------------------------------------------------------------- */}
      <Section
        id="pico"
        title="PICO Framework"
        open={openSections.has("pico")}
        onToggle={() => toggle("pico")}
        description="Define the four dimensions of your review question."
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {PICO_FIELDS.map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-zinc-400 mb-1">{label}</label>
              <Input
                value={cfg.pico[key]}
                onChange={(e) => updatePico({ [key]: e.target.value })}
                placeholder={placeholder}
                disabled={disabled || loading}
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
              />
            </div>
          ))}
        </div>
      </Section>

      {/* ----------------------------------------------------------------- */}
      {/* Section 3: Keywords                                                */}
      {/* ----------------------------------------------------------------- */}
      <Section
        id="keywords"
        title="Search Keywords"
        open={openSections.has("keywords")}
        onToggle={() => toggle("keywords")}
        badge={cfg.keywords.length || undefined}
        description="Used to build search queries across databases. Press Enter or comma to add each keyword."
      >
        <TagInput
          tags={cfg.keywords}
          onChange={(kws) => updateCfg({ keywords: kws })}
          disabled={disabled || loading}
        />
        <div className="mt-2">
          {!showBulkKw ? (
            <button
              type="button"
              onClick={() => setShowBulkKw(true)}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Paste multiple (comma-separated)
            </button>
          ) : (
            <div className="flex gap-2 mt-1">
              <Input
                value={kwBulk}
                onChange={(e) => setKwBulk(e.target.value)}
                placeholder="keyword1, keyword2, keyword3"
                className="flex-1 h-8 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  if (kwBulk.trim()) {
                    const added = kwBulk
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean)
                    const next = [...cfg.keywords]
                    for (const kw of added) if (!next.includes(kw)) next.push(kw)
                    updateCfg({ keywords: next })
                  }
                  setKwBulk("")
                  setShowBulkKw(false)
                }}
                className="h-8 text-xs border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                Add
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setKwBulk("")
                  setShowBulkKw(false)
                }}
                className="h-8 text-xs text-zinc-500"
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      </Section>

      {/* ----------------------------------------------------------------- */}
      {/* Section 4: Inclusion & Exclusion Criteria                          */}
      {/* ----------------------------------------------------------------- */}
      <Section
        id="criteria"
        title="Inclusion & Exclusion Criteria"
        open={openSections.has("criteria")}
        onToggle={() => toggle("criteria")}
        badge={critCount || undefined}
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div>
            <p className="text-xs font-medium text-green-400/80 mb-2.5">Include</p>
            <CriteriaList
              items={cfg.inclusion_criteria}
              onChange={(items) => updateCfg({ inclusion_criteria: items })}
              placeholder="Studies that include..."
              color="green"
              disabled={disabled || loading}
            />
          </div>
          <div>
            <p className="text-xs font-medium text-red-400/80 mb-2.5">Exclude</p>
            <CriteriaList
              items={cfg.exclusion_criteria}
              onChange={(items) => updateCfg({ exclusion_criteria: items })}
              placeholder="Studies that exclude..."
              color="red"
              disabled={disabled || loading}
            />
          </div>
        </div>
      </Section>

      {/* ----------------------------------------------------------------- */}
      {/* Section 5: Sources & Date Range                                    */}
      {/* ----------------------------------------------------------------- */}
      <Section
        id="sources"
        title="Sources & Date Range"
        open={openSections.has("sources")}
        onToggle={() => toggle("sources")}
        description="Select databases to search and the publication year range."
      >
        <div className="flex flex-wrap gap-2 mb-2">
          {DB_OPTIONS.map((db) => {
            const active = cfg.target_databases.includes(db.id)
            return (
              <button
                key={db.id}
                type="button"
                onClick={() => toggleDb(db.id)}
                disabled={disabled || loading}
                className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
                  active
                    ? "bg-violet-600/20 border-violet-500/50 text-violet-300"
                    : "bg-zinc-900 border-zinc-700 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {active && <Check className="h-3 w-3" />}
                {db.label}
              </button>
            )
          })}
        </div>
        <div className="flex items-center gap-1 mb-4">
          <button
            type="button"
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            onClick={() => updateCfg({ target_databases: DB_OPTIONS.map((d) => d.id) })}
          >
            Select all
          </button>
          <span className="text-zinc-700 text-xs mx-0.5">/</span>
          <button
            type="button"
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            onClick={() => updateCfg({ target_databases: [] })}
          >
            None
          </button>
        </div>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">From year</label>
            <Input
              type="number"
              min={1990}
              max={cfg.date_range_end}
              value={cfg.date_range_start}
              onChange={(e) =>
                updateCfg({ date_range_start: parseInt(e.target.value, 10) || 2015 })
              }
              disabled={disabled || loading}
              className="w-24 h-8 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 focus-visible:ring-violet-500/50"
            />
          </div>
          <span className="text-zinc-600 text-sm mb-1.5">to</span>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">To year</label>
            <Input
              type="number"
              min={cfg.date_range_start}
              max={2030}
              value={cfg.date_range_end}
              onChange={(e) =>
                updateCfg({ date_range_end: parseInt(e.target.value, 10) || CURRENT_YEAR })
              }
              disabled={disabled || loading}
              className="w-24 h-8 text-xs bg-zinc-900 border-zinc-800 text-zinc-200 focus-visible:ring-violet-500/50"
            />
          </div>
        </div>
      </Section>

      {/* ----------------------------------------------------------------- */}
      {/* Section 6: API Keys (contextual -- only show keys for selected DBs) */}
      {/* ----------------------------------------------------------------- */}
      {(() => {
        // Compute which credential keys are relevant given selected databases
        const visibleKeys = new Set<string>(["gemini"])
        for (const dbId of cfg.target_databases) {
          for (const credKey of DB_KEY_MAP[dbId] ?? []) {
            visibleKeys.add(credKey)
          }
        }
        const visibleCreds = CRED_META.filter((c) => visibleKeys.has(c.key))

        return (
          <Section
            id="api-keys"
            title="API Keys"
            open={openSections.has("api-keys")}
            onToggle={() => toggle("api-keys")}
            required
          >
            {/* Header row */}
            <div className="flex items-start justify-between mb-3 gap-3">
              <div>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  Saved locally in this browser only -- never sent anywhere except your local backend.
                </p>
                <p className="text-xs text-zinc-600 mt-0.5">
                  Showing credentials for your selected databases above.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowKeys((v) => !v)}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors flex-shrink-0"
              >
                {showKeys ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                {showKeys ? "Hide" : "Reveal"}
              </button>
            </div>

            {/* LLM subsection */}
            <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">LLM</p>
            <div className="flex flex-col gap-3 mb-4">
              {visibleCreds
                .filter((c) => c.key === "gemini")
                .map((cred) => (
                  <CredentialField
                    key={cred.key}
                    cred={cred}
                    value={keys[cred.key as keyof ApiKeyState]}
                    onChange={(v) => setKey(cred.key as keyof ApiKeyState, v)}
                    showKeys={showKeys}
                    disabled={disabled || loading}
                    saved={keysSaved && !!keys[cred.key as keyof ApiKeyState]}
                  />
                ))}
            </div>

            {/* Database credentials subsection (only if any DB keys needed) */}
            {visibleCreds.filter((c) => c.key !== "gemini").length > 0 && (
              <>
                <p className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
                  Database Credentials
                </p>
                <div className="flex flex-col gap-3">
                  {visibleCreds
                    .filter((c) => c.key !== "gemini")
                    .map((cred) => (
                      <CredentialField
                        key={cred.key}
                        cred={cred}
                        value={keys[cred.key as keyof ApiKeyState]}
                        onChange={(v) => setKey(cred.key as keyof ApiKeyState, v)}
                        showKeys={showKeys}
                        disabled={disabled || loading}
                        saved={keysSaved && !!keys[cred.key as keyof ApiKeyState]}
                      />
                    ))}
                </div>
              </>
            )}

            {keysSaved && (
              <button
                type="button"
                onClick={clearKeys}
                className="text-xs text-zinc-600 hover:text-red-400 transition-colors text-left w-fit mt-3"
              >
                Clear saved keys
              </button>
            )}
          </Section>
        )
      })()}

      {/* ----------------------------------------------------------------- */}
      {/* Section 7: Advanced (unified: YAML config + .env import)           */}
      {/* ----------------------------------------------------------------- */}
      <Section
        id="advanced"
        title="Advanced"
        open={advancedOpen}
        onToggle={() => setAdvancedOpen((v) => !v)}
        badge={advancedBadge}
      >
        {/* Inner tab strip */}
        <div className="flex gap-1 mb-4 p-1 bg-zinc-900 rounded-lg border border-zinc-800">
          <button
            type="button"
            onClick={() => setAdvancedTab("yaml")}
            className={`flex-1 text-xs py-1.5 rounded-md transition-colors font-medium ${
              advancedTab === "yaml"
                ? "bg-zinc-700/70 text-zinc-200"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            Review Config (YAML)
          </button>
          <button
            type="button"
            onClick={() => setAdvancedTab("env")}
            className={`flex-1 flex items-center justify-center gap-1.5 text-xs py-1.5 rounded-md transition-colors font-medium ${
              advancedTab === "env"
                ? "bg-zinc-700/70 text-zinc-200"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            <FileKey className="h-3 w-3" />
            Import .env
          </button>
        </div>

        {/* YAML tab */}
        {advancedTab === "yaml" && (
          <div className="flex flex-col gap-3">
            {yamlDirty && (
              <div className="flex items-center justify-between px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                <p className="text-xs text-amber-400/80 flex items-center gap-1.5">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  Manual edits override form fields above
                </p>
                <button
                  type="button"
                  onClick={handleYamlReset}
                  className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors ml-3 flex-shrink-0"
                >
                  Reset to form values
                </button>
              </div>
            )}
            {yamlKeyResult && yamlKeyResult.applied.length > 0 && (
              <div className="flex items-start gap-1.5 px-3 py-2.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-400">
                <Check className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                <span>
                  Detected and applied{" "}
                  <strong>{yamlKeyResult.applied.length}</strong> API key
                  {yamlKeyResult.applied.length !== 1 ? "s" : ""} from{" "}
                  <code className="text-emerald-300/80">api_keys:</code> block --
                  stripped before submission.
                </span>
              </div>
            )}
            <Textarea
              value={yamlText}
              onChange={(e) => handleYamlChange(e.target.value)}
              disabled={disabled || loading}
              rows={18}
              spellCheck={false}
              className="font-mono text-xs resize-y bg-zinc-900 border-zinc-800 text-zinc-300 placeholder:text-zinc-700 focus-visible:ring-violet-500/50"
            />
            <p className="text-xs text-zinc-600 leading-relaxed">
              You can embed an <code className="text-zinc-500">api_keys:</code> block at the
              bottom of this YAML -- keys will be applied to the API Keys section and stripped
              before the file is saved.
            </p>
          </div>
        )}

        {/* .env tab */}
        {advancedTab === "env" && (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-zinc-500 leading-relaxed">
              Paste the contents of a <code className="text-zinc-400">.env</code> file.
              Recognised API key variables will be applied automatically.
            </p>
            <Textarea
              value={envText}
              onChange={(e) => {
                setEnvText(e.target.value)
                setEnvResult(null)
              }}
              onPaste={(e) => {
                const pasted = e.clipboardData.getData("text")
                e.preventDefault()
                setEnvText(pasted)
                setEnvResult(null)
                applyFromEnvText(pasted)
              }}
              placeholder={"GEMINI_API_KEY=AIza...\nPUBMED_EMAIL=you@example.com\nPERPLEXITY_SEARCH_API_KEY=pplx-...\n# any other vars are ignored"}
              disabled={disabled || loading}
              rows={6}
              spellCheck={false}
              className="font-mono text-xs resize-y bg-zinc-900 border-zinc-800 text-zinc-300 placeholder:text-zinc-600 focus-visible:ring-violet-500/50"
            />

            {envResult && (
              <div className={`rounded-lg px-3 py-2.5 text-xs border ${
                envResult.applied.length > 0
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-amber-500/10 border-amber-500/20 text-amber-400"
              }`}>
                {envResult.applied.length > 0 ? (
                  <p className="flex items-start gap-1.5">
                    <Check className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                    <span>
                      Detected and applied{" "}
                      <strong>{envResult.applied.length}</strong> key
                      {envResult.applied.length !== 1 ? "s" : ""}
                      {" "}({envResult.applied.join(", ")}).
                      {envResult.unknown.length > 0 && (
                        <span className="text-zinc-500 ml-1">
                          {envResult.unknown.length} unrecognised var
                          {envResult.unknown.length !== 1 ? "s" : ""} ignored.
                        </span>
                      )}
                    </span>
                  </p>
                ) : (
                  <p className="flex items-start gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
                    No recognised API keys found. Expected variables like{" "}
                    <code className="text-zinc-400">GEMINI_API_KEY</code>,{" "}
                    <code className="text-zinc-400">PUBMED_EMAIL</code>, etc.
                  </p>
                )}
              </div>
            )}

            <div className="flex items-center gap-3">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => applyFromEnvText(envText)}
                disabled={!envText.trim() || disabled || loading}
                className="h-8 text-xs border-zinc-700 text-zinc-300 hover:bg-zinc-800 flex items-center gap-1.5"
              >
                <FileKey className="h-3.5 w-3.5" />
                Apply keys
              </Button>
              {envText && (
                <button
                  type="button"
                  onClick={clearEnv}
                  className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
                >
                  Clear
                </button>
              )}
              <p className="text-xs text-zinc-600 ml-auto leading-relaxed">
                Paste auto-applies. Other vars are ignored.
              </p>
            </div>
          </div>
        )}
      </Section>

      {/* ----------------------------------------------------------------- */}
      {/* Error & submit                                                      */}
      {/* ----------------------------------------------------------------- */}
      {error && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <Button
        type="submit"
        disabled={disabled || loading || !isValid}
        title="Start the systematic review pipeline -- takes 10-60 min"
        className="w-full h-10 mt-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white font-medium gap-2 transition-colors"
      >
        {loading ? (
          <>
            <Loader className="h-4 w-4 animate-spin" />
            Starting review...
          </>
        ) : (
          <>
            <Play className="h-4 w-4" />
            Start Systematic Review
          </>
        )}
      </Button>
    </form>
  )
}
