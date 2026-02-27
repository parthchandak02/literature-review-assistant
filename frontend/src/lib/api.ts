// Typed API wrappers for the FastAPI backend

export interface RunRequest {
  review_yaml: string
  gemini_api_key: string
  openalex_api_key?: string
  ieee_api_key?: string
  pubmed_email?: string
  pubmed_api_key?: string
  perplexity_api_key?: string
  semantic_scholar_api_key?: string
  crossref_email?: string
  run_root?: string
}

export interface RunResponse {
  run_id: string
  topic: string
}

export interface RunInfo {
  run_id: string
  topic: string
  done: boolean
  error: string | null
}

export interface RunResults {
  run_id: string
  outputs: Record<string, unknown>
}

// SSE event types emitted by WebRunContext
export type ReviewEvent =
  | { type: "phase_start"; phase: string; description: string; total: number | null; ts: string }
  | { type: "phase_done"; phase: string; summary: Record<string, unknown>; total: number | null; completed: number | null; ts: string }
  | { type: "progress"; phase: string; current: number; total: number; ts: string }
  | { type: "api_call"; source: string; status: string; phase: string; call_type: string; model: string | null; paper_id: string | null; latency_ms: number | null; tokens_in: number | null; tokens_out: number | null; cost_usd: number | null; records: number | null; details: string | null; section_name: string | null; word_count: number | null; ts: string }
  | { type: "connector_result"; name: string; status: string; records: number; error: string | null; ts: string }
  | { type: "screening_decision"; paper_id: string; stage: string; decision: string; ts: string }
  | { type: "extraction_paper"; paper_id: string; design: string; rob_judgment: string; ts: string }
  | { type: "synthesis"; feasible: boolean; groups: number; n_studies: number; direction: string; ts: string }
  | { type: "rate_limit_wait"; tier: string; slots_used: number; limit: number; ts: string }
  | { type: "db_ready"; ts: string }
  | { type: "workflow_id_ready"; workflow_id: string }
  | { type: "done"; outputs: Record<string, unknown>; ts?: string }
  | { type: "error"; msg: string; ts?: string }
  | { type: "cancelled"; ts?: string }

// Database explorer types
export interface PaperRow {
  paper_id: string
  title: string
  authors: string
  year: number | null
  source_database: string
  doi: string | null
  country: string | null
}

export interface ScreeningRow {
  paper_id: string
  stage: string
  decision: string | null
  rationale: string | null
  created_at: string | null
}

export interface PaperAllRow {
  paper_id: string
  title: string
  authors: string
  year: number | null
  source_database: string
  doi: string | null
  url: string | null
  country: string | null
  ta_decision: string | null
  ft_decision: string | null
  extraction_confidence: number | null
  assessment_source: string | null
}

export interface DbCostRow {
  model: string
  phase: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
  avg_latency_ms: number | null
}

export interface HistoryEntry {
  workflow_id: string
  topic: string
  status: string
  db_path: string
  created_at: string
  updated_at?: string | null
  papers_found?: number | null
  papers_included?: number | null
  total_cost?: number | null
  artifacts_count?: number | null
}

const BASE = "/api"

export async function startRun(req: RunRequest): Promise<RunResponse> {
  const res = await fetch(`${BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function cancelRun(runId: string): Promise<void> {
  const res = await fetch(`${BASE}/cancel/${runId}`, { method: "POST" })
  if (!res.ok) throw await _apiError(res, "Cancel failed")
}

export async function listRuns(): Promise<RunInfo[]> {
  const res = await fetch(`${BASE}/runs`)
  if (!res.ok) return []
  return res.json() as Promise<RunInfo[]>
}

export async function getResults(runId: string): Promise<RunResults> {
  const res = await fetch(`${BASE}/results/${runId}`)
  if (!res.ok) throw new Error("Results not ready")
  return res.json() as Promise<RunResults>
}

export async function getDefaultReviewConfig(): Promise<string> {
  const res = await fetch(`${BASE}/config/review`)
  if (!res.ok) return ""
  const data = await res.json() as { content: string }
  return data.content
}

/**
 * Generate a complete review config YAML from a plain-English research question.
 * Calls the backend LLM endpoint and returns the generated YAML string.
 * Throws an Error with a descriptive message on failure.
 */
export async function generateConfig(researchQuestion: string, geminiApiKey = ""): Promise<string> {
  const res = await fetch(`${BASE}/config/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ research_question: researchQuestion, gemini_api_key: geminiApiKey }),
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json() as { detail?: string }
      if (body.detail) detail = body.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  const data = await res.json() as { yaml: string }
  return data.yaml
}

/** Fetch the review.yaml that was used for a specific past run. Returns null if not available. */
export async function fetchRunConfig(workflowId: string, runRoot = "runs"): Promise<string | null> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history/${encodeURIComponent(workflowId)}/config?${params}`)
  if (!res.ok) return null
  const data = await res.json() as { content: string }
  return data.content ?? null
}

export function downloadUrl(path: string): string {
  return `${BASE}/download?path=${encodeURIComponent(path)}`
}

// Database explorer fetchers

/** Extract a human-readable message from a non-OK response. */
async function _apiError(res: Response, label: string): Promise<Error> {
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json() as { detail?: string }
    if (body.detail) detail = body.detail
  } catch {
    // ignore parse error; use status code
  }
  return new Error(`${label}: ${detail}`)
}

export async function fetchPapers(
  runId: string,
  offset = 0,
  limit = 50,
  search = "",
): Promise<{ total: number; offset: number; limit: number; papers: PaperRow[] }> {
  const params = new URLSearchParams({
    offset: String(offset),
    limit: String(limit),
    search,
  })
  const res = await fetch(`${BASE}/db/${runId}/papers?${params}`)
  if (!res.ok) throw await _apiError(res, "Papers fetch failed")
  return res.json() as Promise<{ total: number; offset: number; limit: number; papers: PaperRow[] }>
}

export async function fetchScreening(
  runId: string,
  stage = "",
  decision = "",
  offset = 0,
  limit = 100,
): Promise<{ total: number; offset: number; limit: number; decisions: ScreeningRow[] }> {
  const params = new URLSearchParams({
    stage,
    decision,
    offset: String(offset),
    limit: String(limit),
  })
  const res = await fetch(`${BASE}/db/${runId}/screening?${params}`)
  if (!res.ok) throw await _apiError(res, "Screening fetch failed")
  return res.json() as Promise<{ total: number; offset: number; limit: number; decisions: ScreeningRow[] }>
}

export async function fetchPapersAll(
  runId: string,
  search = "",
  taDecision = "",
  ftDecision = "",
  year = "",
  source = "",
  country = "",
  offset = 0,
  limit = 50,
  title = "",
  author = "",
): Promise<{ total: number; offset: number; limit: number; papers: PaperAllRow[] }> {
  const params = new URLSearchParams({
    search,
    title,
    author,
    ta_decision: taDecision,
    ft_decision: ftDecision,
    year,
    source,
    country,
    offset: String(offset),
    limit: String(limit),
  })
  const res = await fetch(`${BASE}/db/${runId}/papers-all?${params}`)
  if (!res.ok) throw await _apiError(res, "Papers fetch failed")
  return res.json() as Promise<{ total: number; offset: number; limit: number; papers: PaperAllRow[] }>
}

export async function fetchPapersFacets(
  runId: string,
): Promise<{ years: number[]; sources: string[]; countries: string[]; ta_decisions: string[]; ft_decisions: string[] }> {
  const res = await fetch(`${BASE}/db/${runId}/papers-facets`)
  if (!res.ok) throw await _apiError(res, "Facets fetch failed")
  return res.json() as Promise<{ years: number[]; sources: string[]; countries: string[]; ta_decisions: string[]; ft_decisions: string[] }>
}

export async function fetchPapersSuggest(
  runId: string,
  column: "title" | "author",
  q: string,
): Promise<{ suggestions: string[] }> {
  const params = new URLSearchParams({ column, q })
  const res = await fetch(`${BASE}/db/${runId}/papers-suggest?${params}`)
  if (!res.ok) throw await _apiError(res, "Suggest fetch failed")
  return res.json() as Promise<{ suggestions: string[] }>
}

export async function fetchDbCosts(
  runId: string,
): Promise<{ total_cost: number; records: DbCostRow[] }> {
  const res = await fetch(`${BASE}/db/${runId}/costs`)
  if (!res.ok) throw await _apiError(res, "Costs fetch failed")
  return res.json() as Promise<{ total_cost: number; records: DbCostRow[] }>
}

// Run artifacts + export

export interface ExportResult {
  submission_dir: string
  files: string[]
}

/**
 * Fetch run_summary.json artifacts for any run (live or historically attached).
 * Returns the `artifacts` map of label -> absolute file path.
 */
export async function fetchArtifacts(runId: string): Promise<Record<string, string>> {
  const res = await fetch(`${BASE}/run/${runId}/artifacts`)
  if (!res.ok) throw await _apiError(res, "Artifacts fetch failed")
  const data = await res.json() as { artifacts?: Record<string, string>; outputs?: Record<string, string> }
  return (data.artifacts ?? data.outputs ?? {}) as Record<string, string>
}

/**
 * Trigger IEEE LaTeX export for a completed run.
 * Returns the submission directory path and a sorted list of generated file paths.
 */
export async function triggerExport(runId: string): Promise<ExportResult> {
  const res = await fetch(`${BASE}/run/${runId}/export`, { method: "POST" })
  if (!res.ok) throw await _apiError(res, "Export failed")
  return res.json() as Promise<ExportResult>
}

// Run event log (replay buffer for reconnect and historical views)

export async function fetchRunEvents(runId: string): Promise<ReviewEvent[]> {
  const res = await fetch(`${BASE}/run/${runId}/events`)
  if (!res.ok) return []
  const data = await res.json() as { events?: ReviewEvent[] }
  return data.events ?? []
}

/**
 * Fetch the full event log for a completed workflow directly from SQLite,
 * without needing a prior POST /api/history/attach call.  Use this to load
 * historical events after a page refresh when the run is no longer in the
 * in-memory _active_runs registry.
 */
export async function fetchWorkflowEvents(workflowId: string): Promise<ReviewEvent[]> {
  const res = await fetch(`${BASE}/workflow/${workflowId}/events`)
  if (!res.ok) return []
  const data = await res.json() as { events?: ReviewEvent[] }
  return data.events ?? []
}

// ---------------------------------------------------------------------------
// localStorage helpers -- persist the live run across page refreshes so SSE
// can reconnect and the user does not lose progress tracking on reload.
// ---------------------------------------------------------------------------

export interface StoredLiveRun {
  runId: string
  topic: string
  startedAt: string  // ISO string
  workflowId?: string | null
}

const LIVE_RUN_KEY = "litreview_live_run"

export function saveLiveRun(run: StoredLiveRun): void {
  try {
    localStorage.setItem(LIVE_RUN_KEY, JSON.stringify(run))
  } catch {
    // ignore quota / security errors
  }
}

export function loadLiveRun(): StoredLiveRun | null {
  try {
    const raw = localStorage.getItem(LIVE_RUN_KEY)
    return raw ? (JSON.parse(raw) as StoredLiveRun) : null
  } catch {
    return null
  }
}

export function clearLiveRun(): void {
  try {
    localStorage.removeItem(LIVE_RUN_KEY)
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// localStorage helpers -- persist API keys locally (never sent to any server
// other than the user's own local backend).
// ---------------------------------------------------------------------------

export interface StoredApiKeys {
  gemini: string
  openalex: string
  ieee: string
  pubmedEmail: string
  pubmedApiKey: string
  perplexity: string
  semanticScholar: string
  crossrefEmail: string
}

const API_KEYS_KEY = "litreview_api_keys"

export function saveApiKeys(keys: StoredApiKeys): void {
  try {
    localStorage.setItem(API_KEYS_KEY, JSON.stringify(keys))
  } catch {
    // ignore quota / security errors
  }
}

export function loadApiKeys(): StoredApiKeys | null {
  try {
    const raw = localStorage.getItem(API_KEYS_KEY)
    return raw ? (JSON.parse(raw) as StoredApiKeys) : null
  } catch {
    return null
  }
}

export function clearApiKeys(): void {
  try {
    localStorage.removeItem(API_KEYS_KEY)
  } catch {
    // ignore
  }
}

// Human-in-the-loop screening endpoints

export interface ScreenedPaper {
  paper_id: string
  title: string
  authors: string
  year: number | null
  source_database: string
  doi: string | null
  abstract: string | null
  stage: string
  decision: "include" | "uncertain" | "exclude"
  rationale: string | null
  confidence: number | null
}

export interface ScreeningSummary {
  run_id: string
  total: number
  papers: ScreenedPaper[]
  instructions: string
}

export async function fetchScreeningSummary(runId: string): Promise<ScreeningSummary> {
  const res = await fetch(`${BASE}/run/${runId}/screening-summary`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<ScreeningSummary>
}

export async function approveScreening(runId: string): Promise<void> {
  const res = await fetch(`${BASE}/run/${runId}/approve-screening`, { method: "POST" })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
}

// PRISMA checklist

export interface PrismaChecklistItem {
  item_id: string
  section: string
  description: string
  status: "REPORTED" | "PARTIAL" | "MISSING"
  rationale: string
}

export interface PrismaChecklist {
  run_id: string
  total: number
  reported_count: number
  partial_count: number
  missing_count: number
  passed: boolean
  items: PrismaChecklistItem[]
}

export async function fetchPrismaChecklist(runId: string): Promise<PrismaChecklist> {
  const res = await fetch(`${BASE}/run/${runId}/prisma-checklist`)
  if (!res.ok) throw await _apiError(res, "PRISMA checklist fetch failed")
  return res.json() as Promise<PrismaChecklist>
}

// Living review refresh

export async function livingRefresh(runId: string): Promise<RunResponse> {
  const res = await fetch(`${BASE}/run/${runId}/living-refresh`, { method: "POST" })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Living refresh failed: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

// History endpoints

export async function fetchHistory(runRoot = "runs"): Promise<HistoryEntry[]> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history?${params}`)
  if (!res.ok) return []
  return res.json() as Promise<HistoryEntry[]>
}

export async function attachHistory(entry: HistoryEntry): Promise<RunResponse> {
  const res = await fetch(`${BASE}/history/attach`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: entry.workflow_id,
      topic: entry.topic,
      db_path: entry.db_path,
      status: entry.status,
    }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to attach history: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function resumeRun(entry: HistoryEntry): Promise<RunResponse> {
  const res = await fetch(`${BASE}/history/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: entry.workflow_id,
      db_path: entry.db_path,
      topic: entry.topic,
    }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to resume run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}
