import { useCallback, useEffect, useRef, useState } from "react"

const BASE = import.meta.env.VITE_API_URL ?? ""
const MAX_LINES = 1000
const RECONNECT_DELAY_MS = 3000

export interface LogStreamState {
  lines: string[]
  connected: boolean
  error: string | null
}

/**
 * Stream per-run app.jsonl log lines from the backend.
 *
 * Pass the run's run_id and the hook will connect to
 * /api/logs/stream?run_id={runId}, which serves the per-run app.jsonl
 * file scoped to exactly that run (live or historical attached run).
 *
 * Auto-reconnects on disconnect with a fixed delay.
 */
export function useLogStream(
  runId: string | null,
  enabled = false,
): LogStreamState & { clear: () => void } {
  const [lines, setLines] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enabledRef = useRef(enabled)
  const runIdRef = useRef(runId)

  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { runIdRef.current = runId }, [runId])

  const clear = useCallback(() => setLines([]), [])

  const connect = useCallback(() => {
    if (!enabledRef.current || !runIdRef.current) return

    const url = `${BASE}/api/logs/stream?run_id=${encodeURIComponent(runIdRef.current)}`
    const es = new EventSource(url)
    esRef.current = es
    setError(null)

    es.addEventListener("log", (e: MessageEvent<string>) => {
      setConnected(true)
      const line = e.data
      setLines((prev) => {
        const next = [...prev, line]
        return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next
      })
    })

    es.onerror = () => {
      setConnected(false)
      es.close()
      esRef.current = null
      if (enabledRef.current && runIdRef.current) {
        setError("Log stream reconnecting...")
        reconnectTimerRef.current = setTimeout(() => {
          if (enabledRef.current) connect()
        }, RECONNECT_DELAY_MS)
      } else {
        setError("Log stream disconnected")
      }
    }
  }, [])

  useEffect(() => {
    if (!enabled || !runId) {
      esRef.current?.close()
      esRef.current = null
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      setConnected(false)
      return
    }

    connect()

    return () => {
      esRef.current?.close()
      esRef.current = null
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      setConnected(false)
    }
  }, [enabled, runId, connect])

  return { lines, connected, error, clear }
}
