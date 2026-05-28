import { API_BASE } from "./internal"

export interface NotesStreamEvent {
  workflow_id: string
  note: string
}

/** Subscribe to the global notes SSE stream. Returns an unsubscribe function. */
export function subscribeNotesStream(
  onMessage: (event: NotesStreamEvent) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/notes/stream`)
  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data as string) as NotesStreamEvent
      onMessage(data)
    } catch {
      // Ignore malformed events.
    }
  }
  es.onerror = () => {
    // EventSource auto-reconnects after errors.
  }
  return () => es.close()
}
