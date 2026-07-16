import { apiFetch } from "./client"
import { downloadUrl } from "./urls"

export interface ExportResult {
  submission_dir: string
  files: string[]
}

/** Fetch artifact file contents as plain text (e.g. manuscript markdown). */
export async function fetchArtifactText(path: string, signal?: AbortSignal): Promise<string> {
  const res = await fetch(downloadUrl(path), { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.text()
}

/**
 * Fetch run_summary.json artifacts for any run (live or historically attached).
 * Returns the `artifacts` map of label -> absolute file path.
 */
export async function fetchArtifacts(
  runId: string,
  options?: { workflowIdFallback?: string | null },
): Promise<Record<string, string>> {
  const targetId = options?.workflowIdFallback || runId
  const data = await apiFetch<{ artifacts?: Record<string, string>; outputs?: Record<string, string> }>(
    `/run/${targetId}/artifacts`,
  )
  return (data.artifacts ?? data.outputs ?? {}) as Record<string, string>
}

/**
 * Trigger IEEE LaTeX export for a completed run.
 * When force=false (default), the backend returns existing files immediately if
 * submission/ was already pre-populated by FinalizeNode.
 */
export async function triggerExport(runId: string, force = false): Promise<ExportResult> {
  return apiFetch(`/run/${runId}/export?force=${force}`, { method: "POST" })
}
