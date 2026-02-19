// Typed API wrappers for the FastAPI backend

export interface RunRequest {
  review_yaml: string
  gemini_api_key: string
  openalex_api_key?: string
  ieee_api_key?: string
  log_root?: string
  output_root?: string
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
  | { type: "done"; outputs: Record<string, unknown> }
  | { type: "error"; msg: string }
  | { type: "cancelled" }

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
  await fetch(`${BASE}/cancel/${runId}`, { method: "POST" })
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

export function downloadUrl(path: string): string {
  return `${BASE}/download?path=${encodeURIComponent(path)}`
}
