import { startTransition, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { fetchEventSource } from "@microsoft/fetch-event-source"
import { fetchRunEvents, fetchWorkflowEvents } from "@/lib/api"
import type { ReviewEvent } from "@/lib/api"

export interface SSEState {
  events: ReviewEvent[]
  status: "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled"
  error: string | null
}

const SSE_FLUSH_INTERVAL_MS = 250
const MAX_UI_EVENTS = 2000
const PREFETCH_CHUNK_SIZE = 300
const DEV_PERF_LOG = import.meta.env.DEV

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

function stableStringify(value: unknown): string {
  if (value == null) return String(value)
  if (typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) {
    return `[${value.map((v) => stableStringify(v)).join(",")}]`
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`)
  return `{${entries.join(",")}}`
}

function eventKey(ev: ReviewEvent): string {
  if (ev.id) return `id:${ev.id}`
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
      return [
        base,
        (ev as { paper_id?: string }).paper_id ?? "",
        (ev as { section_name?: string }).section_name ?? "",
        (ev as { status?: string }).status ?? "",
        (ev as { model?: string | null }).model ?? "",
        (ev as { latency_ms?: number | null }).latency_ms ?? "",
        (ev as { tokens_in?: number | null }).tokens_in ?? "",
        (ev as { tokens_out?: number | null }).tokens_out ?? "",
      ].join("|")
    default:
      return `${base}|${stableStringify(ev)}`
  }
}

function normalizeEvent(ev: ReviewEvent): ReviewEvent {
  // Some terminal events may be emitted without ts. Use a deterministic
  // placeholder to keep replay dedup stable across reconnects.
  if ((ev.type === "done" || ev.type === "error" || ev.type === "cancelled") && !("ts" in ev && ev.ts)) {
    return { ...ev, ts: "__missing_terminal_ts__" }
  }
  return ev
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
    const ev = normalizeEvent(events[i])
    const key = eventKey(ev)
    if (!seen.has(key)) {
      seen.add(key)
      out.push(ev)
    }
  }
  return out
}

function isPhaseMarker(ev: ReviewEvent): ev is Extract<ReviewEvent, { type: "phase_start" | "phase_done" | "progress" }> {
  return ev.type === "phase_start" || ev.type === "phase_done" || ev.type === "progress"
}

function capEvents(events: ReviewEvent[], maxEvents: number): ReviewEvent[] {
  if (events.length <= maxEvents) return events

  const byKey = new Map<string, ReviewEvent>()
  for (let i = 0; i < events.length; i++) {
    const ev = normalizeEvent(events[i])
    byKey.set(eventKey(ev), ev)
  }

  const protectedKeys = new Set<string>()

  for (let i = events.length - 1; i >= 0; i--) {
    const ev = normalizeEvent(events[i])
    if (ev.type === "done" || ev.type === "error" || ev.type === "cancelled") {
      protectedKeys.add(eventKey(ev))
      break
    }
  }

  const protectedPhaseNames = new Set<string>()
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = normalizeEvent(events[i])
    if (!isPhaseMarker(ev)) continue
    if (protectedPhaseNames.has(ev.phase)) continue
    protectedPhaseNames.add(ev.phase)
    protectedKeys.add(eventKey(ev))
  }

  const tail = events.slice(-maxEvents).map(normalizeEvent)
  const tailKeys = new Set(tail.map((ev) => eventKey(ev)))
  const missingProtected: ReviewEvent[] = []
  protectedKeys.forEach((k) => {
    if (!tailKeys.has(k)) {
      const ev = byKey.get(k)
      if (ev) missingProtected.push(ev)
    }
  })

  let merged = dedup([...missingProtected, ...tail])
  if (merged.length <= maxEvents) return merged

  let toDrop = merged.length - maxEvents
  const protectedInMerged = new Set(
    merged
      .map((ev) => eventKey(normalizeEvent(ev)))
      .filter((k) => protectedKeys.has(k)),
  )

  const trimmed: ReviewEvent[] = []
  for (let i = 0; i < merged.length; i++) {
    const ev = normalizeEvent(merged[i])
    const k = eventKey(ev)
    if (toDrop > 0 && !protectedInMerged.has(k)) {
      toDrop--
      continue
    }
    trimmed.push(ev)
  }

  if (trimmed.length > maxEvents) {
    merged = trimmed.slice(-maxEvents)
  } else {
    merged = trimmed
  }
  return merged
}

function mergeForUi(previous: ReviewEvent[], incoming: ReviewEvent[]): ReviewEvent[] {
  return capEvents(dedup([...previous, ...incoming]), MAX_UI_EVENTS)
}

type SetState = React.Dispatch<React.SetStateAction<SSEState>>

/**
 * Open an SSE connection to /api/stream/{runId}.
 * Incoming events are merged (with deduplication) into existing state.
 * If the stream returns 404 and workflowId is provided, falls back to
 * replaying historical events from SQLite (handles PM2 restarts).
 */
function openStream(runId: string, signal: AbortSignal, setState: SetState, workflowId?: string | null): void {
  const pending: ReviewEvent[] = []
  let flushTimer: number | null = null

  const clearFlushTimer = () => {
    if (flushTimer != null) {
      window.clearTimeout(flushTimer)
      flushTimer = null
    }
  }

  const flushPending = () => {
    clearFlushTimer()
    if (pending.length === 0) return
    const batch = pending.splice(0, pending.length)
    const startedAt = performance.now()
    startTransition(() => {
      setState((s) => {
        const merged = mergeForUi(s.events, batch)
        const terminal = [...batch].reverse().find(
          (e) => e.type === "done" || e.type === "error" || e.type === "cancelled",
        )
        const status =
          terminal?.type === "done"
            ? "done"
            : terminal?.type === "error"
            ? "error"
            : terminal?.type === "cancelled"
            ? "cancelled"
            : s.status
        if (DEV_PERF_LOG) {
          const elapsed = performance.now() - startedAt
          console.debug("[SSE flush]", {
            batchSize: batch.length,
            eventsBefore: s.events.length,
            eventsAfter: merged.length,
            elapsedMs: Math.round(elapsed),
          })
        }
        return {
          events: merged,
          status,
          error: terminal?.type === "error" ? terminal.msg : s.error,
        }
      })
    })
  }

  const scheduleFlush = () => {
    if (flushTimer != null) return
    flushTimer = window.setTimeout(flushPending, SSE_FLUSH_INTERVAL_MS)
  }

  signal.addEventListener("abort", clearFlushTimer, { once: true })

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
        const data = normalizeEvent(JSON.parse(ev.data) as ReviewEvent)
        pending.push(data)
        if (data.type === "done" || data.type === "error" || data.type === "cancelled") {
          flushPending()
          return
        }
        scheduleFlush()
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
      flushPending()
      setState((s) => (s.status === "streaming" ? { ...s, status: "connecting" } : s))
    },
    openWhenHidden: true,
  }).catch(() => {
    flushPending()
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

  // workflowId is kept in a ref so that changes to it (e.g. workflow_id_ready
  // firing and setting the real workflowId from null) do NOT restart the SSE
  // connection. The ref is always current when openStream reads it.
  const workflowIdRef = useRef(workflowId)
  useLayoutEffect(() => {
    workflowIdRef.current = workflowId
  })

  const reset = useCallback(() => {
    setState({ events: [], status: "idle", error: null })
  }, [])

  useEffect(() => {
    if (!runId) return

    const ctrl = new AbortController()
    abortRef.current = ctrl

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((s) => ({ ...s, status: "connecting", error: null }))

    const appendPriorInChunks = (priorEvents: ReviewEvent[], onDone: () => void) => {
      let offset = 0
      const pushNext = () => {
        if (ctrl.signal.aborted) return
        const chunk = priorEvents.slice(offset, offset + PREFETCH_CHUNK_SIZE)
        if (chunk.length === 0) {
          onDone()
          return
        }
        offset += chunk.length
        startTransition(() => {
          setState((s) => ({
            ...s,
            events: mergeForUi(s.events, chunk),
          }))
        })
        window.setTimeout(pushNext, 0)
      }
      pushNext()
    }

    // Phase 1: prefetch any events already buffered on the backend (handles
    // page refresh during a live run and reconnect after network glitch).
    fetchRunEvents(runId)
      .then((prior) => {
        if (ctrl.signal.aborted) return

        if (prior.length > 0) {
          // Check if the run already has a terminal event in the buffer.
          // Use the LAST terminal event so resumed runs (which have an old
          // "cancelled" event followed by new phase events) open SSE correctly.
          const normalizedPrior = dedup(prior)
          const terminal = [...normalizedPrior].reverse().find(
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
              events: capEvents(normalizedPrior, MAX_UI_EVENTS),
              status,
              error: terminal.type === "error" ? terminal.msg : null,
            })
            // Run already finished -- no need to open the SSE stream.
            return
          }
          // Seed state with prior events before streaming begins.
          if (normalizedPrior.length > PREFETCH_CHUNK_SIZE) {
            appendPriorInChunks(normalizedPrior, () => {
              if (!ctrl.signal.aborted) {
                openStream(runId, ctrl.signal, setState, workflowIdRef.current)
              }
            })
            return
          }
          startTransition(() => {
            setState((s) => ({
              ...s,
              events: mergeForUi(s.events, normalizedPrior),
            }))
          })
        }

        // Phase 2: open live SSE stream for remaining / future events.
        // Use the ref so the 404 fallback has the latest workflowId without
        // this effect re-running (which would abort+restart the connection).
        openStream(runId, ctrl.signal, setState, workflowIdRef.current)
      })
      .catch(() => {
        // fetchRunEvents failed (backend offline) -- still try opening SSE directly.
        if (!ctrl.signal.aborted) {
          openStream(runId, ctrl.signal, setState, workflowIdRef.current)
        }
      })

    return () => {
      ctrl.abort()
    }
  // workflowId intentionally excluded -- kept in workflowIdRef to avoid
  // restarting the SSE connection when workflow_id_ready fires.
   
  }, [runId])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setState((s) => ({ ...s, status: "cancelled" }))
  }, [])

  return { ...state, abort, reset }
}
