import { API_BASE } from "./internal"

export interface WorkflowActiveRunEvent {
  workflow_id: string
  run_id: string
  topic: string
}

export interface SubscribeWorkflowActiveRunCallbacks {
  onAnnouncement: (event: WorkflowActiveRunEvent) => void
  onError?: () => void
}

/** Subscribe to workflow-scoped SSE that announces when a run becomes active. */
export function subscribeWorkflowActiveRun(
  workflowId: string,
  callbacks: SubscribeWorkflowActiveRunCallbacks,
): () => void {
  const es = new EventSource(
    `${API_BASE}/stream/workflow/${encodeURIComponent(workflowId)}`,
  )
  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data as string) as Partial<WorkflowActiveRunEvent>
      if (!data.run_id) return
      callbacks.onAnnouncement({
        workflow_id: data.workflow_id ?? workflowId,
        run_id: data.run_id,
        topic: data.topic ?? "",
      })
    } catch {
      // Ignore malformed events.
    }
  }
  es.onerror = () => {
    callbacks.onError?.()
  }
  return () => es.close()
}
