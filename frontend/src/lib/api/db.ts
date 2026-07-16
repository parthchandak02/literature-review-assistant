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
  total_rows: number
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
): Promise<{ total: number; offset: number; limit: number; papers: PaperAllRow[] }> {
  const safeOffset = sanitizePageNumber(offset, 0)
  const safeLimit = sanitizePageNumber(limit, 50, 1)
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
  return apiFetch(`/db/${runId}/papers-all?${params}`)
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
  return apiFetch(`/db/${runId}/papers-facets`)
}

export async function fetchPapersSuggest(
  runId: string,
  column: "title" | "author",
  q: string,
): Promise<{ suggestions: string[] }> {
  const params = new URLSearchParams({ column, q })
  return apiFetch(`/db/${runId}/papers-suggest?${params}`)
}

export async function fetchGradeSof(
  runId: string,
  options?: { attachPending?: boolean },
): Promise<GradeSofResponse | null> {
  if (options?.attachPending) return null
  try {
    return await apiFetch<GradeSofResponse>(`/run/${encodeURIComponent(runId)}/grade-sof`)
  } catch (err) {
    if (err instanceof APIResponseError && err.status === 404) return null
    throw err
  }
}

export async function fetchDbTables(runId: string): Promise<ExtractedTablesResponse> {
  return apiFetch(`/db/${encodeURIComponent(runId)}/tables`)
}

export function prosperoFormDocxUrl(runId: string): string {
  return `${API_BASE}/run/${encodeURIComponent(runId)}/prospero-form.docx`
}

export function prosperoFormMarkdownUrl(runId: string): string {
  return `${API_BASE}/run/${encodeURIComponent(runId)}/prospero-form.md`
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
