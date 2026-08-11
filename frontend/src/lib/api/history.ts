import { API_BASE } from "./internal"
import type { HistoryEntry, HistoryRailEntry, RunResponse } from "./types"

export function railEntryToHistoryEntry(rail: HistoryRailEntry): HistoryEntry {
  return {
    workflow_id: rail.workflow_id,
    topic: rail.topic,
    status: rail.status,
    db_path: rail.db_path,
    created_at: rail.created_at,
    updated_at: null,
    papers_found: rail.papers_found ?? null,
    papers_included: rail.papers_included ?? null,
    total_cost: rail.total_cost ?? null,
    artifacts_count: null,
    stats_ok: rail.stats_ok ?? null,
    stats_error: null,
    live_run_id: rail.live_run_id ?? null,
    notes: rail.notes ?? null,
    is_archived: rail.is_archived ?? false,
    archived_at: null,
    is_completed_hidden: rail.is_completed_hidden ?? false,
    completed_hidden_at: null,
  }
}

export async function fetchHistoryRail(
  runRootOrOptions: string | { runRoot?: string; stats?: boolean } = "runs",
  options?: { stats?: boolean },
): Promise<HistoryRailEntry[]> {
  const runRoot =
    typeof runRootOrOptions === "string" ? runRootOrOptions : (runRootOrOptions.runRoot ?? "runs")
  const stats =
    typeof runRootOrOptions === "string"
      ? (options?.stats ?? true)
      : (runRootOrOptions.stats ?? true)
  const params = new URLSearchParams({
    run_root: runRoot,
    view: "rail",
    stats: String(stats),
  })
  const res = await fetch(`${API_BASE}/history?${params}`, { cache: "no-store" })
  if (!res.ok) {
    const text = await res.text()
    const detail = text.trim() || "no response body"
    throw new Error(`Failed to fetch history rail (${res.status}): ${detail}`)
  }
  return res.json() as Promise<HistoryRailEntry[]>
}

export async function fetchHistory(runRoot = "runs"): Promise<HistoryEntry[]> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${API_BASE}/history?${params}`, { cache: "no-store" })
  if (!res.ok) {
    const text = await res.text()
    const detail = text.trim() || "no response body"
    throw new Error(`Failed to fetch history (${res.status}): ${detail}`)
  }
  return res.json() as Promise<HistoryEntry[]>
}

export async function attachHistory(entry: HistoryEntry): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/history/attach`, {
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

export async function fetchActiveRun(workflowId: string): Promise<RunResponse | null> {
  const res = await fetch(
    `${API_BASE}/history/active-run?workflow_id=${encodeURIComponent(workflowId)}`,
  )
  if (res.status === 404) return null
  if (!res.ok) return null
  return res.json() as Promise<RunResponse>
}

export async function resumeRun(
  entry: HistoryEntry,
  fromPhase?: string | null,
): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/history/resume`, {
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
  const res = await fetch(`${API_BASE}/history/${workflowId}?${params}`, {
    method: "DELETE",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to delete run: ${text}`)
  }
}

export async function archiveRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${API_BASE}/history/${workflowId}/archive?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to archive run: ${text}`)
  }
}

export async function restoreRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${API_BASE}/history/${workflowId}/restore?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to restore run: ${text}`)
  }
}

export async function hideCompletedRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${API_BASE}/history/${workflowId}/complete-hide?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to move completed run: ${text}`)
  }
}

export async function restoreCompletedRun(workflowId: string, runRoot = "runs"): Promise<void> {
  const params = new URLSearchParams({ run_root: runRoot })
  const res = await fetch(`${API_BASE}/history/${workflowId}/complete-restore?${params}`, {
    method: "POST",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to restore completed run: ${text}`)
  }
}

export async function saveNote(
  workflowId: string,
  note: string,
  runRoot = "runs",
): Promise<void> {
  const res = await fetch(`${API_BASE}/notes/${workflowId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note, run_root: runRoot }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Failed to save note: ${text}`)
  }
}
