// ---------------------------------------------------------------------------
// Pure humanizers that turn backend identifiers into user-facing copy.
// ---------------------------------------------------------------------------

import { runStatusLabel } from "@/lib/constants"

/** `secondary_review` -> "Secondary review". Also accepts kebab-case and camelCase. */
export function humanizeSnake(value: string | null | undefined): string {
  if (!value) return ""
  const words = value
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_\-\s]+/g, " ")
    .trim()
  if (!words) return ""
  const lower = words.toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}

const IDENTIFIER_ACRONYMS: Record<string, string> = {
  rag: "RAG",
  prisma: "PRISMA",
  grade: "GRADE",
  llm: "LLM",
  pdf: "PDF",
  doi: "DOI",
  casp: "CASP",
  mmat: "MMAT",
  rob: "RoB",
  rob2: "RoB 2",
  bm25: "BM25",
  id: "ID",
  json: "JSON",
  csv: "CSV",
  url: "URL",
}

/** Like humanizeSnake, but keeps domain acronyms: `rag_chunk_coverage` -> "RAG chunk coverage". */
export function humanizeIdentifier(value: string | null | undefined): string {
  const sentence = humanizeSnake(value)
  if (!sentence) return ""
  return sentence
    .split(" ")
    .map((word, index) => {
      const acronym = IDENTIFIER_ACRONYMS[word.toLowerCase()]
      if (acronym) return acronym
      return index === 0 ? word : word.toLowerCase()
    })
    .join(" ")
}

/** Label for any raw run status, via resolveRunStatus + STATUS_LABEL. */
export function humanizeStatus(status: string | null | undefined): string {
  return runStatusLabel(status)
}

const STAGE_LABELS: Record<string, string> = {
  title_abstract: "Title and abstract",
  fulltext: "Full text",
  full_text: "Full text",
  calibration: "Calibration",
}

/** Screening stage ids (`title_abstract`, `fulltext`, `calibration`). */
export function humanizeStage(stage: string | null | undefined): string {
  if (!stage) return ""
  const key = stage.trim().toLowerCase()
  return STAGE_LABELS[key] ?? humanizeSnake(key)
}

const SOURCE_LABELS: Record<string, string> = {
  semantic_scholar: "Semantic Scholar",
  semanticscholar: "Semantic Scholar",
  openalex: "OpenAlex",
  openalex_content: "OpenAlex",
  pubmed: "PubMed",
  medline: "PubMed",
  pmc: "PMC",
  crossref: "Crossref",
  arxiv: "arXiv",
  scopus: "Scopus",
  embase: "Embase",
  cinahl: "CINAHL",
  europe_pmc: "Europe PMC",
  europepmc: "Europe PMC",
  unpaywall: "Unpaywall",
  sciencedirect: "ScienceDirect",
  core: "CORE",
  biorxiv: "bioRxiv",
  medrxiv: "medRxiv",
  biorxiv_medrxiv: "bioRxiv/medRxiv",
  web_of_science: "Web of Science",
  wos: "Web of Science",
  ieee: "IEEE Xplore",
  ieee_xplore: "IEEE Xplore",
  dblp: "DBLP",
  clinicaltrials_gov: "ClinicalTrials.gov",
  citation_chasing: "Citation chasing",
  perplexity_search: "Perplexity",
  perplexity_web: "Perplexity web",
  publisher_direct: "Publisher",
  manual: "Manual upload",
  other: "Other",
}

const SOURCE_SUFFIX = /_(?:pdf|text|link|session)$/

/** Search connector / retrieval source ids (`semantic_scholar`, `unpaywall_pdf`) -> display names. */
export function humanizeSource(raw: string | null | undefined): string {
  if (!raw) return ""
  let key = raw.trim().toLowerCase().replace(/[\s-]+/g, "_")
  for (;;) {
    const label = SOURCE_LABELS[key]
    if (label) return label
    const stripped = key.replace(SOURCE_SUFFIX, "")
    if (stripped === key || !stripped) return humanizeSnake(raw)
    key = stripped
  }
}

const RETRIEVAL_LABELS: Record<string, string> = {
  abstract: "Abstract only",
  landing_page_pdf: "Publisher Page (PDF)",
  url_direct_pdf: "Publisher Page (PDF)",
  landing_page_text: "Publisher Page (Text)",
  url_direct_text: "Publisher Page (Text)",
  landing_page: "Publisher Page (Text)",
}

/** Full-text retrieval source (`abstract`, `landing_page_pdf`, `unpaywall_pdf`) -> badge label. */
export function humanizeRetrievalSource(raw: string | null | undefined): string {
  const key = (raw ?? "").trim().toLowerCase()
  return RETRIEVAL_LABELS[key] ?? humanizeSource(raw)
}

export interface ShortModelName {
  name: string
  provider: string | null
}

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  fireworks: "Fireworks",
  "google-gla": "Google",
  "google-vertex": "Google Vertex",
  google: "Google",
  groq: "Groq",
  openai: "OpenAI",
  openrouter: "OpenRouter",
}

function providerLabel(id: string): string {
  return PROVIDER_LABELS[id.toLowerCase()] ?? humanizeSnake(id)
}

const DATE_SUFFIX = /-(?:\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$/

/**
 * `accounts/fireworks/models/deepseek-v4-pro-0813` -> { name: "deepseek-v4-pro", provider: "Fireworks" }.
 * Handles `provider:model`, path-style ids, and trailing date snapshots.
 */
export function shortModelName(modelPath: string | null | undefined): ShortModelName {
  const raw = (modelPath ?? "").trim()
  if (!raw) return { name: "", provider: null }

  let provider: string | null = null
  let rest = raw
  const colon = rest.indexOf(":")
  if (colon > 0) {
    provider = rest.slice(0, colon)
    rest = rest.slice(colon + 1)
  }

  const segments = rest.split("/").filter(Boolean)
  const accountsIdx = segments.indexOf("accounts")
  if (!provider && accountsIdx >= 0 && segments[accountsIdx + 1]) {
    provider = segments[accountsIdx + 1]
  } else if (!provider && segments.length > 1) {
    provider = segments[0]
  }

  const tail = segments[segments.length - 1] ?? rest
  const name = tail.replace(DATE_SUFFIX, "") || tail
  return { name, provider: provider ? providerLabel(provider) : null }
}

export interface LogTagInfo {
  label: string
  description: string
}

/** Glossary for every tag emitted by lib/logLine.ts. */
export const LOG_TAG_GLOSSARY: Record<string, LogTagInfo> = {
  PHASE: { label: "Phase started", description: "A pipeline phase began." },
  DONE: { label: "Done", description: "A phase or the whole review finished." },
  PROG: { label: "Progress", description: "Items processed so far in the current phase." },
  TIMER: { label: "Timing", description: "How long a step took or has been running." },
  "...": { label: "Status", description: "A general status update from the pipeline." },
  CALIB: {
    label: "Calibration",
    description: "Screening thresholds were tuned on a sample. Kappa measures reviewer agreement.",
  },
  LLM: { label: "AI call", description: "A request to a language model, with latency, tokens and cost." },
  SEARCH: { label: "Search", description: "Results from one database search." },
  SRCHOV: {
    label: "Search override",
    description: "Whether a custom database query was applied, missed, or absent.",
  },
  INCLUDE: { label: "Included", description: "A paper passed screening." },
  EXCLUDE: { label: "Excluded", description: "A paper was screened out, with the reason." },
  AUTO: { label: "Rule-based", description: "Decided by an automatic rule, not an AI reviewer." },
  PDF: { label: "Full text", description: "Attempt to retrieve a paper's full-text PDF." },
  EXTRACT: {
    label: "Extraction",
    description: "Data extracted from a paper, with study design and risk-of-bias judgment.",
  },
  SYNTH: { label: "Synthesis", description: "Whether studies can be pooled, and into how many groups." },
  RATELIMIT: { label: "Rate limit", description: "Waiting for a model provider's rate limit to clear." },
  DB: { label: "Database", description: "The run database is ready to browse." },
  ERROR: { label: "Error", description: "Something failed. See the message for details." },
  WARN: { label: "Warning", description: "Needs attention, but the run did not crash." },
  CANCEL: { label: "Cancelled", description: "The review was stopped." },
  FUNNEL: {
    label: "Screening funnel",
    description: "Papers remaining after deduplication, metadata checks and automatic exclusions.",
  },
  QA: {
    label: "Quality check",
    description: "A sample of rule-based exclusions set aside for manual review.",
  },
  BATCH: {
    label: "Relevance pre-screen",
    description: "An AI pass that scores papers in batches and forwards likely matches to full review.",
  },
  CAP: {
    label: "Safety valve",
    description: "More papers were forwarded because the tail of the ranking still had relevant hits.",
  },
}

/** Glossary entry for a log tag such as `PROG`, `SRCHOV`, `[AUTO]` or `...`. */
export function humanizeLogTag(tag: string | null | undefined): LogTagInfo {
  const key = (tag ?? "").trim().replace(/^\[|\]$/g, "").toUpperCase()
  if (!key) return { label: "", description: "" }
  if (/^\.+$/.test(key)) return LOG_TAG_GLOSSARY["..."]
  return LOG_TAG_GLOSSARY[key] ?? { label: humanizeSnake(key.toLowerCase()), description: "" }
}

const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  ndash: "–",
  mdash: "—",
  hellip: "…",
  lsquo: "‘",
  rsquo: "’",
  ldquo: "“",
  rdquo: "”",
  laquo: "«",
  raquo: "»",
  copy: "©",
  reg: "®",
  trade: "™",
  deg: "°",
  plusmn: "±",
  times: "×",
  divide: "÷",
  le: "≤",
  ge: "≥",
  ne: "≠",
  micro: "µ",
  middot: "·",
  bull: "•",
  alpha: "α",
  beta: "β",
  gamma: "γ",
  delta: "δ",
  kappa: "κ",
  mu: "μ",
  chi: "χ",
  eacute: "é",
  egrave: "è",
  aacute: "á",
  oacute: "ó",
  uuml: "ü",
  ouml: "ö",
  auml: "ä",
  ntilde: "ñ",
  ccedil: "ç",
}

const CASE_INSENSITIVE_ENTITIES = new Set(["amp", "lt", "gt", "quot", "apos", "nbsp"])

const ENTITY_PATTERN = /&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]*);/gi

function decodeOnce(value: string): string {
  return value.replace(ENTITY_PATTERN, (match, body: string) => {
    if (body[0] === "#") {
      const hex = body[1] === "x" || body[1] === "X"
      const code = Number.parseInt(body.slice(hex ? 2 : 1), hex ? 16 : 10)
      if (!Number.isFinite(code) || code <= 0 || code > 0x10ffff) return match
      return String.fromCodePoint(code)
    }
    const lower = body.toLowerCase()
    return NAMED_ENTITIES[body] ?? (CASE_INSENSITIVE_ENTITIES.has(lower) ? NAMED_ENTITIES[lower] : match)
  })
}

/** Decode HTML entities, including double-encoded ones like `students&amp;apos;`. */
export function decodeHtmlEntities(value: string | null | undefined, maxPasses = 3): string {
  let current = value ?? ""
  for (let pass = 0; pass < maxPasses && current.includes("&"); pass += 1) {
    const next = decodeOnce(current)
    if (next === current) break
    current = next
  }
  return current
}
