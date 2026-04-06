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
  wos_api_key?: string
  scopus_api_key?: string
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
type ReviewEventIdentity = { id?: string }

/** Present on SSE events when the backend labels durability for replay contracts. */
export type EventDurability = "durable" | "eventual"

export type ReviewEvent = (
  | ({ type: "phase_start"; phase: string; description: string; total: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "phase_done"; phase: string; summary: Record<string, unknown>; total: number | null; completed: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "progress"; phase: string; current: number; total: number; ts: string } & ReviewEventIdentity)
  | ({ type: "api_call"; source: string; status: string; phase: string; call_type: string; model: string | null; paper_id: string | null; latency_ms: number | null; tokens_in: number | null; tokens_out: number | null; cost_usd: number | null; records: number | null; details: string | null; section_name: string | null; word_count: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "connector_result"; name: string; status: string; records: number; query?: string; error: string | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_decision"; paper_id: string; stage: string; decision: string; confidence?: number; title?: string; reason?: string; method?: "llm" | "heuristic"; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "extraction_paper"; paper_id: string; design: string; rob_judgment: string; ts: string } & ReviewEventIdentity)
  | ({ type: "synthesis"; feasible: boolean; groups: number; n_studies: number; direction: string; ts: string } & ReviewEventIdentity)
  | ({ type: "rate_limit_wait"; tier: string; slots_used: number; limit: number; waited_seconds?: number; ts: string } & ReviewEventIdentity)
  | ({ type: "rate_limit_resolved"; tier: string; waited_seconds: number; ts: string } & ReviewEventIdentity)
  | ({ type: "search_override_status"; database: string; status: "applied" | "miss" | "absent"; detail: string; ts: string } & ReviewEventIdentity)
  | ({ type: "status"; message: string; ts: string } & ReviewEventIdentity)
  | ({ type: "screening_prefilter_done"; deduped: number; metadata_rejected: number; after_metadata: number; automation_excluded: number; to_llm: number; dual_review_cap?: number | null; bm25_validation_forwarded?: number; empty_abstract_pool?: number; empty_abstract_excluded?: number; empty_abstract_rescued?: number; reason_breakdown?: Record<string, number>; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "deterministic_exclusion_qa_sample"; sample_size: number; pool_size: number; items: Array<{ paper_id: string; reason_code: string; title: string }>; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "batch_screen_done"; scored: number; forwarded: number; excluded: number; skipped_resume: number; threshold: number; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_cap_overflow"; trigger: string; validation_tail_n: number; validation_tail_forwarded: number; validation_tail_forward_rate: number; trigger_threshold: number; overflow_candidates: number; overflow_evaluated: number; overflow_forwarded: number; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_calibration"; include_threshold: number; exclude_threshold: number; kappa: number; iterations: number; sample_size: number; ts: string } & ReviewEventIdentity)
  | ({ type: "pdf_result"; paper_id: string; title: string; source: string; success: boolean; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "db_ready"; ts: string } & ReviewEventIdentity)
  | ({ type: "workflow_id_ready"; workflow_id: string } & ReviewEventIdentity)
  | ({ type: "done"; outputs: Record<string, unknown>; ts?: string } & ReviewEventIdentity)
  | ({ type: "error"; msg: string; traceback?: string; ts?: string } & ReviewEventIdentity)
  | ({ type: "cancelled"; ts?: string } & ReviewEventIdentity)
) & { durability?: EventDurability }

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
  primary_study_status: string | null
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

export interface DbCostAggregateBucketRow {
  bucket: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface DbCostAggregateGroupRow {
  group_key: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface DbCostAggregateTotals {
  total_cost_usd: number
  total_calls: number
  total_tokens_in: number
  total_tokens_out: number
}

export interface DbCostAggregatesResponse {
  run_id: string
  start_ts: string | null
  end_ts: string | null
  totals: DbCostAggregateTotals
  by_day: DbCostAggregateBucketRow[]
  by_week: DbCostAggregateBucketRow[]
  by_month: DbCostAggregateBucketRow[]
  by_workflow: DbCostAggregateGroupRow[]
  by_phase: DbCostAggregateGroupRow[]
  by_model: DbCostAggregateGroupRow[]
}

export interface HistoryCostAggregatesResponse {
  run_root: string
  start_ts: string | null
  end_ts: string | null
  include_archived: boolean
  workflow_count: number
  totals: DbCostAggregateTotals
  by_day: DbCostAggregateBucketRow[]
  by_week: DbCostAggregateBucketRow[]
  by_month: DbCostAggregateBucketRow[]
  by_workflow: DbCostAggregateGroupRow[]
  by_phase: DbCostAggregateGroupRow[]
  by_model: DbCostAggregateGroupRow[]
}

export type DbCostExportGranularity = "day" | "week" | "month"

export interface DbCostAggregateParams {
  start_ts?: string
  end_ts?: string
}

export interface DbCostExportParams extends DbCostAggregateParams {
  granularity?: DbCostExportGranularity
}

export interface HistoryCostAggregateParams extends DbCostAggregateParams {
  run_root?: string
  include_archived?: boolean
}

export interface HistoryCostExportParams extends HistoryCostAggregateParams {
  granularity?: DbCostExportGranularity
}

export interface ScreeningDiagnostics {
  batch_parse_degraded: number
  batch_id_mismatch: number
  batch_missing_fallback: number
  contract_violation_count: number
  fast_path_include: number
  fast_path_exclude: number
  cross_reviewed: number
}

export interface ValidationSummary {
  workflow_id: string
  latest_run: {
    validation_run_id: string
    profile: string
    status: string
    tool_version: string
    summary: Record<string, unknown>
    started_at: string
    completed_at: string
    error_count: number
    warn_count: number
    total_checks: number
  } | null
}

export interface ValidationCheck {
  phase: string
  check_name: string
  status: string
  severity: string
  metric_value: number | null
  details: Record<string, unknown>
  source_module: string | null
  paper_id: string | null
  created_at: string
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
  stats_ok?: boolean | null
  stats_error?: string | null
  /** Set when the workflow has an active in-process task. The frontend uses
   *  this to connect a live SSE stream instead of replaying historical DB events. */
  live_run_id?: string | null
  /** User-authored annotation persisted in the central registry. */
  notes?: string | null
  /** Soft archive metadata for sidebar grouping. */
  is_archived?: boolean
  archived_at?: string | null
}

const BASE = "/api"

export class APIResponseError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = "APIResponseError"
    this.status = status
    this.detail = detail
  }
}

function _sanitizePageNumber(value: number, fallback: number, minValue = 0): number {
  if (!Number.isFinite(value)) return fallback
  const normalized = Math.trunc(value)
  if (normalized < minValue) return fallback
  return normalized
}

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

/**
 * Start a review run from a pre-assembled master list CSV.
 * The CSV is uploaded as multipart/form-data alongside the review YAML and API keys.
 * SearchNode will load papers from the CSV instead of querying databases.
 * Every downstream phase (screening, extraction, synthesis, writing) runs identically.
 */
export async function startRunWithMasterlist(
  csvFile: File,
  reviewYaml: string,
  keys: StoredApiKeys,
  runRoot = "runs",
): Promise<RunResponse> {
  const form = new FormData()
  form.append("csv_file", csvFile)
  form.append("review_yaml", reviewYaml)
  form.append("gemini_api_key", keys.gemini)
  if (keys.openalex) form.append("openalex_api_key", keys.openalex)
  if (keys.ieee) form.append("ieee_api_key", keys.ieee)
  if (keys.pubmedEmail) form.append("pubmed_email", keys.pubmedEmail)
  if (keys.pubmedApiKey) form.append("pubmed_api_key", keys.pubmedApiKey)
  if (keys.perplexity) form.append("perplexity_api_key", keys.perplexity)
  if (keys.semanticScholar) form.append("semantic_scholar_api_key", keys.semanticScholar)
  if (keys.crossrefEmail) form.append("crossref_email", keys.crossrefEmail)
  if (keys.wos) form.append("wos_api_key", keys.wos)
  if (keys.scopus) form.append("scopus_api_key", keys.scopus)
  if (runRoot) form.append("run_root", runRoot)
  const res = await fetch(`${BASE}/run-with-masterlist`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start master list run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

/**
 * Start a review run with connector search plus one supplementary CSV import.
 * The uploaded CSV is merged with connector results before dedup and screening.
 */
export async function startRunWithSupplementaryCsv(
  csvFile: File,
  reviewYaml: string,
  keys: StoredApiKeys,
  runRoot = "runs",
): Promise<RunResponse> {
  const form = new FormData()
  form.append("csv_file", csvFile)
  form.append("review_yaml", reviewYaml)
  form.append("gemini_api_key", keys.gemini)
  if (keys.openalex) form.append("openalex_api_key", keys.openalex)
  if (keys.ieee) form.append("ieee_api_key", keys.ieee)
  if (keys.pubmedEmail) form.append("pubmed_email", keys.pubmedEmail)
  if (keys.pubmedApiKey) form.append("pubmed_api_key", keys.pubmedApiKey)
  if (keys.perplexity) form.append("perplexity_api_key", keys.perplexity)
  if (keys.semanticScholar) form.append("semantic_scholar_api_key", keys.semanticScholar)
  if (keys.crossrefEmail) form.append("crossref_email", keys.crossrefEmail)
  if (keys.wos) form.append("wos_api_key", keys.wos)
  if (keys.scopus) form.append("scopus_api_key", keys.scopus)
  if (runRoot) form.append("run_root", runRoot)
  const res = await fetch(`${BASE}/run-with-supplementary-csv`, {
    method: "POST",
    body: form,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to start supplementary CSV run: ${text}`)
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

/**
 * Streaming version of generateConfig. Calls the SSE endpoint, invoking
 * onProgress with each step key and metadata as the backend progresses through stages.
 * Resolves with the final YAML string when done.
 *
 * Steps emitted by backend: "start" -> "web_research" -> "web_research_done"
 *   -> "structuring" -> "finalizing" -> (done event with yaml)
 */
export async function generateConfigStream(
  researchQuestion: string,
  geminiApiKey: string,
  onProgress: (step: string, metadata?: Record<string, unknown>) => void,
): Promise<string> {
  const res = await fetch(`${BASE}/config/generate/stream`, {
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
  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body from config generation stream")
  const decoder = new TextDecoder()
  let buffer = ""
  let yaml = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      try {
        const msg = JSON.parse(line.slice(6)) as {
          type: string
          step?: string
          yaml?: string
          quality?: Record<string, unknown>
          detail?: string
          [key: string]: unknown
        }
        if (msg.type === "progress" && msg.step) {
          const metadata: Record<string, unknown> = {}
          for (const [key, value] of Object.entries(msg)) {
            if (key !== "type" && key !== "step") {
              metadata[key] = value
            }
          }
          onProgress(msg.step, metadata)
        } else if (msg.type === "done" && msg.yaml) {
          yaml = msg.yaml
        } else if (msg.type === "error") {
          throw new Error(msg.detail ?? "Config generation failed")
        }
      } catch (parseErr) {
        if (parseErr instanceof Error && parseErr.message !== "Config generation failed") continue
        throw parseErr
      }
    }
  }
  if (!yaml) throw new Error("Config generation completed without producing a config")
  return yaml
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

export function submissionZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/submission.zip`
}

export function studyFilesZipUrl(runId: string): string {
  return `${BASE}/run/${runId}/studies-files.zip`
}

// Database explorer fetchers

/** Extract a human-readable message from a non-OK response. */
async function _apiError(res: Response, label: string): Promise<Error> {
  let detail: unknown = `HTTP ${res.status}`
  let message = `HTTP ${res.status}`
  try {
    const body = await res.json() as { detail?: unknown }
    if ("detail" in body) {
      detail = body.detail
      if (typeof body.detail === "string") {
        message = body.detail
      } else if (
        body.detail &&
        typeof body.detail === "object" &&
        "message" in body.detail &&
        typeof (body.detail as { message?: unknown }).message === "string"
      ) {
        message = (body.detail as { message: string }).message
      }
    }
  } catch {
    // ignore parse error; use status code
  }
  return new APIResponseError(`${label}: ${message}`, res.status, detail)
}

export async function fetchPapers(
  runId: string,
  offset = 0,
  limit = 50,
  search = "",
): Promise<{ total: number; offset: number; limit: number; papers: PaperRow[] }> {
  const safeOffset = _sanitizePageNumber(offset, 0)
  const safeLimit = _sanitizePageNumber(limit, 50, 1)
  const params = new URLSearchParams({
    offset: String(safeOffset),
    limit: String(safeLimit),
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
  const safeOffset = _sanitizePageNumber(offset, 0)
  const safeLimit = _sanitizePageNumber(limit, 100, 1)
  const params = new URLSearchParams({
    stage,
    decision,
    offset: String(safeOffset),
    limit: String(safeLimit),
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
  primaryStatus = "",
  year = "",
  source = "",
  country = "",
  offset = 0,
  limit = 50,
  title = "",
  author = "",
): Promise<{ total: number; offset: number; limit: number; papers: PaperAllRow[] }> {
  const safeOffset = _sanitizePageNumber(offset, 0)
  const safeLimit = _sanitizePageNumber(limit, 50, 1)
  const params = new URLSearchParams({
    search,
    title,
    author,
    ta_decision: taDecision,
    ft_decision: ftDecision,
    primary_status: primaryStatus,
    year,
    source,
    country,
    offset: String(safeOffset),
    limit: String(safeLimit),
  })
  const res = await fetch(`${BASE}/db/${runId}/papers-all?${params}`)
  if (!res.ok) throw await _apiError(res, "Papers fetch failed")
  return res.json() as Promise<{ total: number; offset: number; limit: number; papers: PaperAllRow[] }>
}

export async function fetchPapersFacets(
  runId: string,
): Promise<{
  years: number[]
  sources: string[]
  countries: string[]
  ta_decisions: string[]
  ft_decisions: string[]
  primary_statuses: string[]
}> {
  const res = await fetch(`${BASE}/db/${runId}/papers-facets`)
  if (!res.ok) throw await _apiError(res, "Facets fetch failed")
  return res.json() as Promise<{
    years: number[]
    sources: string[]
    countries: string[]
    ta_decisions: string[]
    ft_decisions: string[]
    primary_statuses: string[]
  }>
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
): Promise<{ total_cost: number; records: DbCostRow[]; screening_diagnostics?: ScreeningDiagnostics }> {
  const res = await fetch(`${BASE}/db/${runId}/costs`)
  if (!res.ok) throw await _apiError(res, "Costs fetch failed")
  return res.json() as Promise<{ total_cost: number; records: DbCostRow[]; screening_diagnostics?: ScreeningDiagnostics }>
}

export async function fetchDbCostAggregates(
  runId: string,
  params?: DbCostAggregateParams,
): Promise<DbCostAggregatesResponse> {
  const qs = new URLSearchParams()
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  const res = await fetch(`${BASE}/db/${runId}/costs/aggregates${suffix}`)
  if (!res.ok) throw await _apiError(res, "Cost aggregates fetch failed")
  return res.json() as Promise<DbCostAggregatesResponse>
}

export function getDbCostExportUrl(runId: string, params?: DbCostExportParams): string {
  const qs = new URLSearchParams()
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.granularity) qs.set("granularity", params.granularity)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return `${BASE}/db/${runId}/costs/export${suffix}`
}

export async function fetchHistoryCostAggregates(
  params?: HistoryCostAggregateParams,
  options?: { signal?: AbortSignal },
): Promise<HistoryCostAggregatesResponse> {
  const qs = new URLSearchParams()
  if (params?.run_root) qs.set("run_root", params.run_root)
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.include_archived !== undefined) {
    qs.set("include_archived", String(params.include_archived))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  const res = await fetch(`${BASE}/history/costs/aggregates${suffix}`, {
    cache: "no-store",
    signal: options?.signal,
  })
  if (!res.ok) throw await _apiError(res, "History cost aggregates fetch failed")
  return res.json() as Promise<HistoryCostAggregatesResponse>
}

export function getHistoryCostExportUrl(params?: HistoryCostExportParams): string {
  const qs = new URLSearchParams()
  if (params?.run_root) qs.set("run_root", params.run_root)
  if (params?.start_ts) qs.set("start_ts", params.start_ts)
  if (params?.end_ts) qs.set("end_ts", params.end_ts)
  if (params?.granularity) qs.set("granularity", params.granularity)
  if (params?.include_archived !== undefined) {
    qs.set("include_archived", String(params.include_archived))
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  return `${BASE}/history/costs/export${suffix}`
}

export async function fetchWorkflowValidationSummary(workflowId: string): Promise<ValidationSummary> {
  const res = await fetch(`${BASE}/workflow/${workflowId}/validation/summary`)
  if (!res.ok) throw await _apiError(res, "Validation summary fetch failed")
  return res.json() as Promise<ValidationSummary>
}

export async function fetchWorkflowValidationChecks(
  workflowId: string,
  validationRunId?: string,
): Promise<{ workflow_id: string; validation_run_id: string | null; checks: ValidationCheck[] }> {
  const params = new URLSearchParams()
  if (validationRunId) params.set("validation_run_id", validationRunId)
  const suffix = params.toString() ? `?${params.toString()}` : ""
  const res = await fetch(`${BASE}/workflow/${workflowId}/validation/checks${suffix}`)
  if (!res.ok) throw await _apiError(res, "Validation checks fetch failed")
  return res.json() as Promise<{ workflow_id: string; validation_run_id: string | null; checks: ValidationCheck[] }>
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

export interface ReadinessCheckRow {
  name: string
  ok: boolean
  detail?: string | null
}

export interface ReadinessScorecard {
  workflow_id: string
  ready: boolean
  checks: ReadinessCheckRow[]
  contract_passed: boolean
  blocking_reasons: string[]
}

export async function fetchRunReadiness(runId: string, runRoot = "runs"): Promise<ReadinessScorecard> {
  const q = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/run/${encodeURIComponent(runId)}/readiness?${q.toString()}`)
  if (!res.ok) throw await _apiError(res, "Readiness fetch failed")
  return (await res.json()) as ReadinessScorecard
}

// ---------------------------------------------------------------------------
// References tab -- included papers with full-text file info
// ---------------------------------------------------------------------------

export interface PaperReference {
  paper_id: string
  title: string
  authors: string
  year: number | null
  source_database: string | null
  doi: string | null
  url: string | null
  country: string | null
  retrieval_source: string
  has_file: boolean
  file_type: "pdf" | "txt" | null
}

/**
 * Fetch included papers for the References tab.
 * When runId fails with 404 (evicted from _active_runs), retry with workflowId
 * so the backend can resolve via workflows_registry.
 */
export async function fetchPapersReference(
  runId: string,
  workflowIdFallback?: string | null,
): Promise<PaperReference[]> {
  let res = await fetch(`${BASE}/run/${runId}/papers-reference`)
  if (res.status === 404 && workflowIdFallback && workflowIdFallback !== runId) {
    res = await fetch(`${BASE}/run/${encodeURIComponent(workflowIdFallback)}/papers-reference`)
  }
  if (!res.ok) throw await _apiError(res, "Papers reference fetch failed")
  const data = await res.json() as { papers?: PaperReference[] }
  return data.papers ?? []
}

/** Returns a direct URL to download a paper's full-text file (PDF or TXT). */
export function paperFileUrl(runId: string, paperId: string): string {
  return `${BASE}/run/${runId}/papers/${paperId}/file`
}

export interface FetchPdfsResult {
  attempted: number
  succeeded: number
  failed: number
  skipped: number
  results: Array<{
    paper_id: string
    status: "ok" | "failed" | "skipped"
    source: string | null
    file_type: "pdf" | "txt" | null
    error: string | null
  }>
}

export interface FetchPdfsProgressEvent {
  current: number
  total: number
  paperId: string
  title: string
  status: "ok" | "failed" | "skipped"
  source: string | null
  fileType: "pdf" | "txt" | null
}

/**
 * Retroactively fetch full-text PDFs/text for all included papers in a completed run.
 * Streams SSE progress events as each paper is processed.
 * onProgress is called after each paper with the current count and result.
 * When runId fails with 404, retries with workflowIdFallback (registry lookup).
 */
export async function fetchPdfsForRun(
  runId: string,
  onProgress?: (evt: FetchPdfsProgressEvent) => void,
  workflowIdFallback?: string | null,
): Promise<FetchPdfsResult> {
  let res = await fetch(`${BASE}/run/${runId}/fetch-pdfs`, { method: "POST" })
  if (res.status === 404 && workflowIdFallback && workflowIdFallback !== runId) {
    res = await fetch(`${BASE}/run/${encodeURIComponent(workflowIdFallback)}/fetch-pdfs`, {
      method: "POST",
    })
  }
  if (!res.ok) throw await _apiError(res, "PDF fetch failed")

  const reader = res.body?.getReader()
  if (!reader) throw new Error("No response body from fetch-pdfs stream")

  const decoder = new TextDecoder()
  let buffer = ""
  let result: FetchPdfsResult = { attempted: 0, succeeded: 0, failed: 0, skipped: 0, results: [] }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      try {
        const msg = JSON.parse(line.slice(6)) as {
          type: string
          current?: number
          total?: number
          paper_id?: string
          title?: string
          status?: string
          source?: string | null
          file_type?: "pdf" | "txt" | null
          attempted?: number
          succeeded?: number
          failed?: number
          skipped?: number
          results?: FetchPdfsResult["results"]
          detail?: string
        }
        if (msg.type === "progress" && onProgress) {
          onProgress({
            current: msg.current ?? 0,
            total: msg.total ?? 0,
            paperId: msg.paper_id ?? "",
            title: msg.title ?? "",
            status: (msg.status ?? "failed") as "ok" | "failed" | "skipped",
            source: msg.source ?? null,
            fileType: msg.file_type ?? null,
          })
        } else if (msg.type === "done") {
          result = {
            attempted: msg.attempted ?? 0,
            succeeded: msg.succeeded ?? 0,
            failed: msg.failed ?? 0,
            skipped: msg.skipped ?? 0,
            results: msg.results ?? [],
          }
        } else if (msg.type === "error") {
          throw new Error(msg.detail ?? "PDF fetch failed")
        }
      } catch (parseErr) {
        if (parseErr instanceof SyntaxError) continue
        throw parseErr
      }
    }
  }
  return result
}

/**
 * Trigger IEEE LaTeX export for a completed run.
 * Returns the submission directory path and a sorted list of generated file paths.
 *
 * When force=false (default), the backend returns existing files immediately if
 * submission/ was already pre-populated by FinalizeNode, skipping pdflatex/DOCX.
 * Pass force=true (Refresh button) to force a full re-package.
 */
export async function triggerExport(runId: string, force = false): Promise<ExportResult> {
  const res = await fetch(`${BASE}/run/${runId}/export?force=${force}`, { method: "POST" })
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
  wos: string
  scopus: string
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

/**
 * Fetch API keys that are already configured in the server's environment
 * (i.e. values set in .env).  Returns an object with empty strings for any
 * key not present on the server.  Never throws -- returns all-empty on error.
 */
export async function fetchEnvKeys(): Promise<StoredApiKeys> {
  const empty: StoredApiKeys = {
    gemini: "", openalex: "", ieee: "", pubmedEmail: "", pubmedApiKey: "",
    perplexity: "", semanticScholar: "", crossrefEmail: "", wos: "", scopus: "",
  }
  try {
    const res = await fetch(`${BASE}/config/env-keys`)
    if (!res.ok) return empty
    return { ...empty, ...(await res.json() as Partial<StoredApiKeys>) }
  } catch {
    return empty
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
  reason: string | null
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

export interface ScreeningOverride {
  paper_id: string
  decision: "include" | "exclude"
  reason?: string
}

export async function approveScreening(
  runId: string,
  overrides?: ScreeningOverride[],
): Promise<void> {
  const body = overrides && overrides.length > 0 ? { overrides } : { overrides: [] }
  const res = await fetch(`${BASE}/run/${runId}/approve-screening`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
}

export interface KnowledgeGraphNode {
  id: string
  title: string
  year: number | null
  study_design: string
  community_id: number
  first_author: string
  has_multiple_authors: boolean
}

export interface KnowledgeGraphEdge {
  source: string
  target: string
  rel_type: string
  weight: number
}

export interface KnowledgeCommunity {
  id: number
  paper_ids: string[]
  label: string
}

export interface ResearchGap {
  id: string
  description: string
  gap_type: string
  related_paper_ids: string[]
}

export interface KnowledgeGraph {
  run_id: string
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
  communities: KnowledgeCommunity[]
  gaps: ResearchGap[]
}

export async function fetchKnowledgeGraph(runId: string): Promise<KnowledgeGraph> {
  const res = await fetch(`${BASE}/run/${runId}/knowledge-graph`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<KnowledgeGraph>
}

// PRISMA checklist

export interface PrismaChecklistItem {
  item_id: string
  section: string
  description: string
  status: "REPORTED" | "PARTIAL" | "MISSING" | "NOT_APPLICABLE"
  rationale: string
  applies: boolean
  evidence_terms: string[]
}

export interface PrismaChecklist {
  run_id: string
  source_state: "artifact_missing" | "validated_md" | "validated_tex" | "validated_md_and_tex"
  total: number
  item_total: number
  reported_count: number
  partial_count: number
  missing_count: number
  not_applicable_count: number
  passed: boolean
  items: PrismaChecklistItem[]
}

export async function fetchPrismaChecklist(runId: string): Promise<PrismaChecklist> {
  const res = await fetch(`${BASE}/run/${runId}/prisma-checklist`)
  if (!res.ok) throw await _apiError(res, "PRISMA checklist fetch failed")
  return res.json() as Promise<PrismaChecklist>
}

export interface ManuscriptAuditFinding {
  finding_id: string
  profile: string
  severity: "major" | "minor" | "note"
  category: string
  section: string | null
  evidence: string
  recommendation: string
  owner_module: string
  blocking: boolean
  created_at: string
}

export interface ManuscriptContractViolation {
  code: string
  severity: string
  message: string
  expected: string | null
  actual: string | null
}

export interface ManuscriptAuditRun {
  audit_run_id: string
  workflow_id?: string
  mode: string
  verdict: "accept" | "minor_revisions" | "major_revisions" | "reject"
  passed: boolean
  selected_profiles: string[]
  summary: string
  total_findings: number
  major_count: number
  minor_count: number
  note_count: number
  blocking_count: number
  contract_mode: string
  contract_passed: boolean
  contract_violation_count: number
  contract_violations: ManuscriptContractViolation[]
  gate_blocked: boolean
  gate_failure_reasons: string[]
  total_cost_usd: number
  created_at: string
}

export interface ManuscriptAuditPayload {
  run_id: string
  workflow_id: string
  latest_run: ManuscriptAuditRun | null
  history: ManuscriptAuditRun[]
  findings: ManuscriptAuditFinding[]
}

export async function fetchManuscriptAudit(runId: string): Promise<ManuscriptAuditPayload> {
  const res = await fetch(`${BASE}/run/${runId}/manuscript-audit`)
  if (!res.ok) throw await _apiError(res, "Manuscript audit fetch failed")
  return res.json() as Promise<ManuscriptAuditPayload>
}

export interface WorkflowManuscriptAuditSummary {
  workflow_id: string
  latest_run: ManuscriptAuditRun | null
  history: ManuscriptAuditRun[]
}

export interface WorkflowManuscriptAuditFindings {
  workflow_id: string
  audit_run_id: string | null
  findings: ManuscriptAuditFinding[]
}

export async function fetchWorkflowManuscriptAuditSummary(workflowId: string): Promise<WorkflowManuscriptAuditSummary> {
  const res = await fetch(`${BASE}/workflow/${workflowId}/manuscript-audit/summary`)
  if (!res.ok) throw await _apiError(res, "Manuscript audit summary fetch failed")
  return res.json() as Promise<WorkflowManuscriptAuditSummary>
}

export async function fetchWorkflowManuscriptAuditFindings(
  workflowId: string,
  auditRunId?: string | null,
): Promise<WorkflowManuscriptAuditFindings> {
  const suffix = auditRunId ? `?audit_run_id=${encodeURIComponent(auditRunId)}` : ""
  const res = await fetch(`${BASE}/workflow/${workflowId}/manuscript-audit/findings${suffix}`)
  if (!res.ok) throw await _apiError(res, "Manuscript audit findings fetch failed")
  return res.json() as Promise<WorkflowManuscriptAuditFindings>
}

// History endpoints

export async function fetchHistory(runRoot = "runs"): Promise<HistoryEntry[]> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history?${params}`, { cache: "no-store" })
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

/** Check if a workflow is actively running (e.g. resumed from CLI). Returns run_id if so. */
export async function fetchActiveRun(
  workflowId: string,
): Promise<RunResponse | null> {
  const res = await fetch(`${BASE}/history/active-run?workflow_id=${encodeURIComponent(workflowId)}`)
  if (res.status === 404) return null
  if (!res.ok) return null
  return res.json() as Promise<RunResponse>
}

export async function resumeRun(
  entry: HistoryEntry,
  fromPhase?: string | null,
): Promise<RunResponse> {
  const res = await fetch(`${BASE}/history/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_id: entry.workflow_id,
      db_path: entry.db_path,
      topic: entry.topic,
      ...(fromPhase != null && fromPhase !== "" && { from_phase: fromPhase }),
    }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to resume run: ${text}`)
  }
  return res.json() as Promise<RunResponse>
}

export async function deleteRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history/${workflowId}?${params}`, {
    method: "DELETE",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to delete run: ${text}`)
  }
}

export async function archiveRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history/${workflowId}/archive?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to archive run: ${text}`)
  }
}

export async function restoreRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${BASE}/history/${workflowId}/restore?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to restore run: ${text}`)
  }
}

/** Persist a user note for a workflow. Broadcasts to all connected note-stream clients. */
export async function saveNote(workflowId: string, note: string, runRoot = "runs"): Promise<void> {
  const res = await fetch(`${BASE}/notes/${workflowId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, run_root: runRoot }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to save note: ${text}`)
  }
}
