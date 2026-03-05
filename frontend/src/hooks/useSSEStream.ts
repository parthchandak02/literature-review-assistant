import { useCallback, useEffect, useRef, useState } from "react"
import { fetchEventSource } from "@microsoft/fetch-event-source"
import { fetchRunEvents, fetchWorkflowEvents } from "@/lib/api"
import type { ReviewEvent } from "@/lib/api"

export interface SSEState {
  events: ReviewEvent[]
  status: "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled"
  error: string | null
}

/** Converts raw fetch/network errors to a user-friendly message. */
function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  if (
    err instanceof TypeError ||
    msg.toLowerCase().includes("failed to fetch") ||
    msg.toLowerCase().includes("networkerror") ||
    msg.toLowerCase().includes("load failed")
  ) {
    return "Backend is offline or unreachable"
  }
  if (msg.includes("Stream open failed: 404")) {
    return "Run not found on backend (server may have restarted)"
  }
  return msg
}

function eventKey(ev: ReviewEvent, i: number): string {
  const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""
  const base = `${ev.type}|${ts}`
  switch (ev.type) {
    case "phase_start":
    case "phase_done":
      return `${base}|${(ev as { phase?: string }).phase ?? ""}`
    case "screening_decision":
      return `${base}|${(ev as { paper_id?: string }).paper_id ?? ""}|${(ev as { stage?: string }).stage ?? ""}`
    case "progress":
      return `${base}|${(ev as { phase?: string }).phase ?? ""}|${(ev as { current?: number }).current ?? ""}|${(ev as { total?: number }).total ?? ""}`
    case "connector_result":
      return `${base}|${(ev as { name?: string }).name ?? ""}`
    case "db_ready":
      return base
    case "extraction_paper":
      return `${base}|${(ev as { paper_id?: string }).paper_id ?? ""}`
    case "synthesis":
      return `${base}|${(ev as { feasible?: boolean }).feasible ?? ""}|${(ev as { n_studies?: number }).n_studies ?? ""}`
    case "api_call":
      return `${base}|${(ev as { paper_id?: string }).paper_id ?? ""}|${(ev as { section_name?: string }).section_name ?? ""}|${i}`
    default:
      return `${base}|${i}`
  }
}

/**
 * Deduplicate an event list by content-based keys. Events with identical
 * content (phase, paper_id, etc.) are collapsed to handle prefetch + SSE
 * overlap and effect re-runs.
 */
function dedup(events: ReviewEvent[]): ReviewEvent[] {
  const seen = new Set<string>()
  const out: ReviewEvent[] = []
  for (let i = 0; i < events.length; i++) {
    const ev = events[i]
    const key = eventKey(ev, i)
    if (!seen.has(key)) {
      seen.add(key)
      out.push(ev)
    }
  }
  return out
}

type SetState = React.Dispatch<React.SetStateAction<SSEState>>

/**
 * Open an SSE connection to /api/stream/{runId}.
 * Incoming events are merged (with deduplication) into existing state.
 * If the stream returns 404 and workflowId is provided, falls back to
 * replaying historical events from SQLite (handles PM2 restarts).
 */
function openStream(runId: string, signal: AbortSignal, setState: SetState, workflowId?: string | null): void {
  fetchEventSource(`/api/stream/${runId}`, {
    signal,
    onopen: async (res) => {
      if (res.status === 404 && workflowId) {
        // Backend restarted -- live run is gone but SQLite history may exist.
        // Fall back to replaying historical events from the workflow log.
        fetchWorkflowEvents(workflowId).then((events) => {
          if (signal.aborted) return
          if (events.length > 0) {
            setState({ events: dedup(events), status: "done", error: null })
          } else {
            setState((s) => ({
              ...s,
              status: "error",
              error: "Run not found on backend (server may have restarted)",
            }))
          }
        }).catch(() => {
          if (!signal.aborted) {
            setState((s) => ({
              ...s,
              status: "error",
              error: "Run not found on backend (server may have restarted)",
            }))
          }
        })
        throw new Error("AbortError") // stop fetch-event-source retry loop
      }
      if (!res.ok) throw new Error(`Stream open failed: ${res.status}`)
      setState((s) => ({ ...s, status: "streaming" }))
    },
    onmessage: (ev) => {
      if (ev.event === "heartbeat") return
      try {
        const data = JSON.parse(ev.data) as ReviewEvent
        setState((s) => {
          const merged = dedup([...s.events, data])
          let status = s.status
          if (data.type === "done") status = "done"
          else if (data.type === "error") status = "error"
          else if (data.type === "cancelled") status = "cancelled"
          return {
            events: merged,
            status,
            error: data.type === "error" ? data.msg : s.error,
          }
        })
      } catch {
        // ignore parse errors
      }
    },
    onerror: (err) => {
      const msg = err instanceof Error ? err.message : String(err)
      // Intentional abort (user navigated away, signal cancelled, or 404-SQLite fallback).
      if (msg === "AbortError" || msg.includes("aborted")) throw err
      // Permanent server error (non-2xx open): stop retrying and show the error.
      if (msg.includes("Stream open failed:")) {
        setState((s) => ({ ...s, status: "error", error: friendlyError(err) }))
        throw err
      }
      // Transient network error (connection drop, brief offline, etc.).
      // Do NOT throw -- fetch-event-source will auto-reconnect and will send
      // Last-Event-ID so the server only replays events the client missed.
      setState((s) => (s.status === "streaming" ? { ...s, status: "connecting" } : s))
    },
    openWhenHidden: true,
  }).catch(() => {
    // Absorb the re-thrown error from onerror to prevent unhandled rejection
  })
}

export function useSSEStream(runId: string | null, workflowId?: string | null) {
  const [state, setState] = useState<SSEState>({
    events: [],
    status: "idle",
    error: null,
  })

  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    setState({ events: [], status: "idle", error: null })
  }, [])

  useEffect(() => {
    if (!runId) return

    const ctrl = new AbortController()
    abortRef.current = ctrl

    // eslint-disable-next-line react-hooks/set-state-in-effect -- initializes connecting status on run start
    setState((s) => ({ ...s, status: "connecting", error: null }))

    // Phase 1: prefetch any events already buffered on the backend (handles
    // page refresh during a live run and reconnect after network glitch).
    fetchRunEvents(runId)
      .then((prior) => {
        if (ctrl.signal.aborted) return

        if (prior.length > 0) {
          // Check if the run already has a terminal event in the buffer.
          // Use the LAST terminal event so resumed runs (which have an old
          // "cancelled" event followed by new phase events) open SSE correctly.
          const terminal = [...prior].reverse().find(
            (e) => e.type === "done" || e.type === "error" || e.type === "cancelled",
          )
          if (terminal) {
            const status =
              terminal.type === "done"
                ? "done"
                : terminal.type === "error"
                ? "error"
                : "cancelled"
            setState({
              events: prior,
              status,
              error: terminal.type === "error" ? terminal.msg : null,
            })
            // Run already finished -- no need to open the SSE stream.
            return
          }
          // Seed state with prior events before streaming begins.
          setState((s) => ({
            ...s,
            events: dedup([...s.events, ...prior]),
          }))
        }

        // Phase 2: open live SSE stream for remaining / future events.
        // Pass workflowId so openStream can fall back to SQLite replay on 404.
        openStream(runId, ctrl.signal, setState, workflowId)
      })
      .catch(() => {
        // fetchRunEvents failed (backend offline) -- still try opening SSE directly.
        if (!ctrl.signal.aborted) {
          openStream(runId, ctrl.signal, setState, workflowId)
        }
      })

    return () => {
      ctrl.abort()
    }
  }, [runId, workflowId])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setState((s) => ({ ...s, status: "cancelled" }))
  }, [])

  return { ...state, abort, reset }
}
