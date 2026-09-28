import { APIResponseError, apiFetch } from "./client"
import { API_BASE, apiError, fetchWithWorkflowFallback, sanitizePageNumber } from "./internal"

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

export type PapersFacetField =
  | "ta_decision"
  | "ft_decision"
  | "primary_status"
  | "year"
  | "source"
  | "country"

export interface PapersFacetCount {
  value: string | number | null
  count: number
}

export interface PapersFacets {
  years: number[]
  sources: string[]
  countries: string[]
  ta_decisions: string[]
  ft_decisions: string[]
  primary_statuses: string[]
  counts?: Partial<Record<PapersFacetField, PapersFacetCount[]>>
}

export type PapersSortKey =
  | "title"
  | "year"
  | "source"
  | "ta_decision"
  | "ft_decision"
  | "primary_status"
  | "confidence"

export type SortDir = "asc" | "desc"

/** Missing-value sentinel for exact-match facet filters (e.g. not yet screened). */
export const FACET_NONE = "__none__"

export interface PapersQuery {
  title: string
  author: string
  ta: string[]
  ft: string[]
  primaryStatus: string[]
  source: string[]
  country: string[]
  yearMin: number | null
  yearMax: number | null
}

export interface PapersSort {
  sort: PapersSortKey | null
  dir: SortDir
}

export interface PaperScreeningDecision {
  reviewer_type: string
  decision: string
  reason: string | null
  exclusion_reason: string | null
  confidence: number | null
  created_at: string | null
}

export interface PaperScreeningStage {
  stage: string
  final_decision: string | null
  agreement: boolean | null
  adjudication_needed: boolean | null
  decisions: PaperScreeningDecision[]
}

export interface PaperExtractionSummary {
  study_design: string | null
  primary_study_status: string | null
  extraction_source: string | null
  extraction_confidence: number | null
  participant_count: number | null
  setting: string | null
  country: string | null
  study_duration: string | null
  intervention_description: string | null
  comparator_description: string | null
  results_summary: Record<string, string> | null
  funding_source: string | null
  outcome_count: number
}

export interface PaperQualitySummary {
  tool_used: string
  overall_judgment: string
  assessment_source: string | null
}

export interface PaperDetail {
  paper_id: string
  title: string
  authors: string[]
  year: number | null
  source_database: string | null
  doi: string | null
  url: string | null
  country: string | null
  journal: string | null
  abstract: string | null
  keywords: string[]
  screening: PaperScreeningStage[]
  extraction: PaperExtractionSummary | null
  quality: PaperQualitySummary | null
}

export interface PapersAllResponse {
  total: number
  offset: number
  limit: number
  papers: PaperAllRow[]
  facets?: PapersFacets
}

export interface PapersAllResponseWithFacets extends PapersAllResponse {
  facets: PapersFacets
}

export interface GradeSofRow {
  outcome: string
  studies: number | null
  participants: number | null
  effect: string
  certainty: string
  reasons: string[]
}

export interface GradeSofResponse {
  run_id: string
  topic: string
  rows: GradeSofRow[]
}

export interface ExtractedOutcomeRow {
  name?: string
  effect_size?: number | null
  ci_lower?: number | null
  ci_upper?: number | null
  p_value?: number | null
  n?: number | null
  [key: string]: unknown
}

export interface ExtractedOutcomePaper {
  paper_id: string
  title: string
  doi: string | null
  extraction_source: string
  outcomes: ExtractedOutcomeRow[]
}

export interface ExtractedTablesResponse {
  /** Outcome rows across every page. */
  total_rows: number
  /** Papers with at least one numeric outcome, across every page. */
  total_papers?: number
  offset?: number
  limit?: number | null
  /** True when paper filters restricted the result. */
  filtered?: boolean
  papers: ExtractedOutcomePaper[]
}

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
  options?: { includeFacets?: boolean } | boolean,
): Promise<PapersAllResponse> {
  const safeOffset = sanitizePageNumber(offset, 0)
  const safeLimit = sanitizePageNumber(limit, 50, 1)
  const includeFacets = typeof options === "boolean" ? options : Boolean(options?.includeFacets)
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
  if (includeFacets) {
    params.set("include", "facets")
  }
  return apiFetch(`/db/${runId}/papers-all?${params}`)
}

export async function fetchPapersFacets(runId: string, query?: PapersQuery): Promise<PapersFacets> {
  const qs = query ? `?${papersQueryParams(query)}` : ""
  return apiFetch(`/db/${runId}/papers-facets${qs}`)
}

/** Exact-match, multi-value query params shared by papers-page, papers-facets and papers-export. */
export function papersQueryParams(query: PapersQuery, sort?: PapersSort): URLSearchParams {
  const params = new URLSearchParams({ match: "exact" })
  if (query.title) params.set("title", query.title)
  if (query.author) params.set("author", query.author)
  const multi: Array<[string, string[]]> = [
    ["ta_decision", query.ta],
    ["ft_decision", query.ft],
    ["primary_status", query.primaryStatus],
    ["source", query.source],
    ["country", query.country],
  ]
  for (const [key, values] of multi) {
    for (const v of values) params.append(key, v)
  }
  if (query.yearMin != null) params.set("year_min", String(query.yearMin))
  if (query.yearMax != null) params.set("year_max", String(query.yearMax))
  if (sort?.sort) {
    params.set("sort", sort.sort)
    params.set("dir", sort.dir)
  }
  return params
}

export async function fetchPapersPage(
  runId: string,
  query: PapersQuery,
  sort: PapersSort,
  offset: number,
  limit: number,
): Promise<PapersAllResponse> {
  const params = papersQueryParams(query, sort)
  params.set("offset", String(sanitizePageNumber(offset, 0)))
  params.set("limit", String(sanitizePageNumber(limit, 50, 1)))
  return apiFetch(`/db/${encodeURIComponent(runId)}/papers-all?${params}`)
}

export function papersExportUrl(
  runId: string,
  query: PapersQuery,
  sort: PapersSort,
  format: "csv" | "ris",
): string {
  const params = papersQueryParams(query, sort)
  params.set("format", format)
  return `${API_BASE}/db/${encodeURIComponent(runId)}/papers-export?${params}`
}

export async function fetchPaperDetail(runId: string, paperId: string): Promise<PaperDetail> {
  return apiFetch(`/db/${encodeURIComponent(runId)}/papers/${encodeURIComponent(paperId)}`)
}

export async function fetchPapersSuggest(
  runId: string,
  column: "title" | "author",
  q: string,
): Promise<{ suggestions: string[] }> {
  const params = new URLSearchParams({ column, q })
  return apiFetch(`/db/${runId}/papers-suggest?${params}`)
}

export async function fetchGradeSof(runId: string): Promise<GradeSofResponse | null> {
  try {
    return await apiFetch<GradeSofResponse>(`/run/${encodeURIComponent(runId)}/grade-sof`)
  } catch (err) {
    if (err instanceof APIResponseError && err.status === 404) return null
    throw err
  }
}

/** Numeric outcomes grouped by paper. With `query`, restricted to matching papers; with `page`, paginated by outcome row. */
export async function fetchDbTables(
  runId: string,
  query?: PapersQuery,
  page?: { offset: number; limit: number },
): Promise<ExtractedTablesResponse> {
  const params = query ? papersQueryParams(query) : new URLSearchParams()
  if (page) {
    params.set("offset", String(sanitizePageNumber(page.offset, 0)))
    params.set("limit", String(sanitizePageNumber(page.limit, 50, 1)))
  }
  const qs = params.toString()
  return apiFetch(`/db/${encodeURIComponent(runId)}/tables${qs ? `?${qs}` : ""}`)
}

export function prosperoFormDocxUrl(runId: string): string {
  return `${API_BASE}/run/${encodeURIComponent(runId)}/prospero-form.docx`
}

export function prosperoFormMarkdownUrl(runId: string): string {
  return `${API_BASE}/run/${encodeURIComponent(runId)}/prospero-form.md`
}

export function prismaFlowZipUrl(runId: string): string {
  return `${API_BASE}/run/${encodeURIComponent(runId)}/prisma-flow.zip`
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
  const res = await fetchWithWorkflowFallback(
    runId,
    workflowIdFallback,
    (id) => `${API_BASE}/run/${encodeURIComponent(id)}/papers-reference`,
  )
  if (!res.ok) throw await apiError(res, "Papers reference fetch failed")
  const data = await res.json() as { papers?: PaperReference[] }
  return data.papers ?? []
}

/** Returns a direct URL to download a paper's full-text file (PDF or TXT). */
export function paperFileUrl(runId: string, paperId: string): string {
  return `${API_BASE}/run/${runId}/papers/${paperId}/file`
}
