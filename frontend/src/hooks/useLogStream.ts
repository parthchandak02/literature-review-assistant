import { useCallback, useEffect, useRef, useState } from "react"

const BASE = import.meta.env.VITE_API_URL ?? ""
const MAX_LINES = 1000

export interface LogStreamState {
  lines: string[]
  connected: boolean
  error: string | null
}

export function useLogStream(
  process = "backend",
  logType: "out" | "err" = "out",
  enabled = false,
): LogStreamState & { clear: () => void } {
  const [lines, setLines] = useState<string[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  const clear = useCallback(() => setLines([]), [])

  useEffect(() => {
    if (!enabled) {
      esRef.current?.close()
      esRef.current = null
      setConnected(false)
      return
    }

    const url = `${BASE}/api/logs/stream?process=${encodeURIComponent(process)}&log_type=${logType}`
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
      setError("Log stream disconnected")
    }

    return () => {
      es.close()
      esRef.current = null
      setConnected(false)
    }
  }, [enabled, process, logType])

  return { lines, connected, error, clear }
}
