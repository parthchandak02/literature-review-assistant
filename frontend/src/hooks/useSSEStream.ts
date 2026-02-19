import { useCallback, useEffect, useRef, useState } from "react"
import { fetchEventSource } from "@microsoft/fetch-event-source"
import type { ReviewEvent } from "@/lib/api"

export interface SSEState {
  events: ReviewEvent[]
  status: "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled"
  error: string | null
}

/** Converts raw fetch/network errors to a user-friendly message. */
function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  // Network-level failure (backend down, refused, DNS, timeout)
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

export function useSSEStream(runId: string | null) {
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

    setState((s) => ({ ...s, status: "connecting", error: null }))

    fetchEventSource(`/api/stream/${runId}`, {
      signal: ctrl.signal,
      onopen: async (res) => {
        if (!res.ok) {
          throw new Error(`Stream open failed: ${res.status}`)
        }
        setState((s) => ({ ...s, status: "streaming" }))
      },
      onmessage: (ev) => {
        if (ev.event === "heartbeat") return
        try {
          const data = JSON.parse(ev.data) as ReviewEvent
          setState((s) => {
            const next = [...s.events, data]
            let status = s.status
            if (data.type === "done") status = "done"
            else if (data.type === "error") status = "error"
            else if (data.type === "cancelled") status = "cancelled"
            return {
              events: next,
              status,
              error: data.type === "error" ? data.msg : s.error,
            }
          })
        } catch {
          // ignore parse errors
        }
      },
      onerror: (err) => {
        // Don't surface AbortError from intentional ctrl.abort() calls
        const msg = err instanceof Error ? err.message : String(err)
        if (msg === "AbortError" || msg.includes("aborted")) {
          throw err // stop retrying, onerror already handled
        }
        setState((s) => ({
          ...s,
          status: "error",
          error: friendlyError(err),
        }))
        throw err // stop automatic retry
      },
      openWhenHidden: true,
    }).catch(() => {
      // Absorb the re-thrown error from onerror to prevent unhandled rejection
    })

    return () => {
      ctrl.abort()
    }
  }, [runId])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setState((s) => ({ ...s, status: "cancelled" }))
  }, [])

  return { ...state, abort, reset }
}
