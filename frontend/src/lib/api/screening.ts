import { apiFetch } from "./client"
import { API_BASE, apiError, fetchWithWorkflowFallback } from "./internal"

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

export interface ScreeningOverride {
  paper_id: string
  decision: "include" | "exclude"
  reason?: string
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

export async function fetchScreeningSummary(runId: string): Promise<ScreeningSummary> {
  return apiFetch(`/run/${runId}/screening-summary`)
}

export async function approveScreening(
  runId: string,
  overrides?: ScreeningOverride[],
): Promise<void> {
  const body = overrides && overrides.length > 0 ? { overrides } : { overrides: [] }
  await apiFetch(`/run/${runId}/approve-screening`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

export async function fetchKnowledgeGraph(runId: string): Promise<KnowledgeGraph> {
  return apiFetch(`/run/${runId}/knowledge-graph`)
}

/**
 * Retroactively fetch full-text PDFs/text for all included papers in a completed run.
 * Streams SSE progress events as each paper is processed.
 */
export async function fetchPdfsForRun(
  runId: string,
  onProgress?: (evt: FetchPdfsProgressEvent) => void,
  workflowIdFallback?: string | null,
): Promise<FetchPdfsResult> {
  const res = await fetchWithWorkflowFallback(
    runId,
    workflowIdFallback,
    (id) => `${API_BASE}/run/${encodeURIComponent(id)}/fetch-pdfs`,
    { method: "POST" },
  )
  if (!res.ok) throw await apiError(res, "PDF fetch failed")

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
