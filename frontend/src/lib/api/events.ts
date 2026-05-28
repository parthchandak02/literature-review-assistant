import { shouldFallbackToWorkflowEvents } from "../runSelection"
import { API_BASE } from "./internal"
import type { ReviewEvent } from "./types"

export async function fetchRunEvents(runId: string): Promise<ReviewEvent[]> {
  const res = await fetch(`${API_BASE}/run/${runId}/events`)
  if (!res.ok) return []
  const data = (await res.json()) as { events?: ReviewEvent[] }
  return data.events ?? []
}

export async function fetchWorkflowEvents(workflowId: string): Promise<ReviewEvent[]> {
  const res = await fetch(`${API_BASE}/workflow/${workflowId}/events`)
  if (!res.ok) return []
  const data = (await res.json()) as { events?: ReviewEvent[] }
  return data.events ?? []
}

export async function fetchHistoricalReviewEvents(
  workflowId: string | null | undefined,
  runId: string,
  options?: { attachPending?: boolean },
): Promise<ReviewEvent[]> {
  if (options?.attachPending) {
    return workflowId ? fetchWorkflowEvents(workflowId) : []
  }
  const runEvents = await fetchRunEvents(runId)
  if (workflowId && shouldFallbackToWorkflowEvents(runEvents.length, workflowId)) {
    return fetchWorkflowEvents(workflowId)
  }
  return runEvents
}
