import { useEffect, useMemo, useRef, useState } from "react"
import { fetchEventSource } from "@microsoft/fetch-event-source"
import { Loader2 } from "lucide-react"
import { buildLogsStreamUrl } from "@/lib/api"

type StructuredStreamStatus = "connecting" | "streaming" | "error"

interface StructuredLogLine {
  id: string
  raw: string
  summary: string
  searchable: string
  parsed: Record<string, unknown> | null
}

interface StructuredLogViewerProps {
  runId?: string | null
  workflowId?: string | null
  searchQuery: string
}

const MAX_STRUCTURED_LINES = 5000

function summarizeStructuredPayload(payload: Record<string, unknown>): string {
  const ts = typeof payload.timestamp === "string" ? payload.timestamp : "-"
  const event = typeof payload.event === "string" ? payload.event : "log"
  const level = typeof payload.level === "string" ? payload.level.toUpperCase() : "INFO"
  const detailKeys = [
    "phase",
    "call_type",
    "status",
    "source",
    "connector",
    "paper_id",
    "section_name",
    "decision",
  ] as const
  const details = detailKeys
    .map((key) => {
      const value = payload[key]
      if (value == null || value === "") return null
      return `${key}=${String(value)}`
    })
    .filter(Boolean)
    .join(" ")
  return `[${ts}] ${event} ${level}${details ? ` ${details}` : ""}`
}

function parseStructuredLine(raw: string, index: number): StructuredLogLine {
  try {
    const parsedValue = JSON.parse(raw)
    if (typeof parsedValue === "object" && parsedValue !== null && !Array.isArray(parsedValue)) {
      const parsed = parsedValue as Record<string, unknown>
      const summary = summarizeStructuredPayload(parsed)
      return {
        id: `struct-${index}`,
        raw,
        summary,
        searchable: `${summary} ${raw}`.toLowerCase(),
        parsed,
      }
    }
  } catch {
    // Keep non-JSON lines verbatim (e.g. waiting placeholders).
  }
  return {
    id: `struct-${index}`,
    raw,
    summary: raw,
    searchable: raw.toLowerCase(),
    parsed: null,
  }
}

function StructuredLogViewerBody({ runId, workflowId, searchQuery }: StructuredLogViewerProps) {
  const [lines, setLines] = useState<StructuredLogLine[]>([])
  const [status, setStatus] = useState<StructuredStreamStatus>("connecting")
  const [error, setError] = useState<string | null>(null)
  const counterRef = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    counterRef.current = 0

    const ctrl = new AbortController()
    const streamUrl = buildLogsStreamUrl({ runId, workflowId })

    fetchEventSource(streamUrl, {
      signal: ctrl.signal,
      openWhenHidden: true,
      onopen: async (res) => {
        if (!res.ok) {
          throw new Error(`Stream open failed: ${res.status}`)
        }
        setStatus("streaming")
      },
      onmessage: (msg) => {
        if (msg.event !== "log") return
        const line = parseStructuredLine(msg.data, counterRef.current++)
        setLines((prev) => {
          const next = [...prev, line]
          return next.length > MAX_STRUCTURED_LINES ? next.slice(next.length - MAX_STRUCTURED_LINES) : next
        })
      },
      onerror: (err) => {
        const msg = err instanceof Error ? err.message : String(err)
        if (msg === "AbortError" || msg.includes("aborted")) throw err
        if (msg.includes("Stream open failed:")) {
          setStatus("error")
          setError(msg.includes("404") ? "Structured log not found for this run." : msg)
          throw err
        }
        setStatus("error")
        setError(msg)
        throw err
      },
    }).catch(() => {
      // Intentionally swallow rejected promise from fetch-event-source callbacks.
    })

    return () => ctrl.abort()
  }, [runId, workflowId])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" })
  }, [lines.length])

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return lines
    return lines.filter((line) => line.searchable.includes(q))
  }, [lines, searchQuery])

  return (
    <div className="h-[clamp(22rem,calc(100dvh-20rem),40rem)] w-full rounded-xl border border-border bg-background overflow-hidden flex flex-col">
      <div className="px-4 py-2 border-b border-border/70 flex items-center justify-between text-[11px]">
        <span className="text-muted tabular-nums">{filtered.length} lines</span>
        {status === "connecting" ? (
          <span className="flex items-center gap-1.5 text-intent-primary">
            <Loader2 className="h-3 w-3 animate-spin" />
            Connecting...
          </span>
        ) : status === "streaming" ? (
          <span className="text-intent-success">Streaming app.jsonl</span>
        ) : (
          <span className="text-intent-danger">Disconnected</span>
        )}
      </div>
      <div ref={containerRef} className="flex-1 overflow-y-auto font-mono text-[11px] p-4 leading-5 space-y-1">
        {error && <div className="text-intent-danger">{error}</div>}
        {!error && filtered.length === 0 && (
          <div className="text-muted">No structured log lines yet for this filter.</div>
        )}
        {filtered.map((line) => {
          return (
            <div key={line.id} className="border-l-2 border-border pl-2">
              {line.parsed ? (
                <pre className="text-[10px] text-foreground whitespace-pre-wrap break-all">
                  {JSON.stringify(line.parsed, null, 2)}
                </pre>
              ) : (
                <div className="whitespace-pre-wrap break-all text-muted">{line.raw}</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function StructuredLogViewer(props: StructuredLogViewerProps) {
  const streamKey = `${props.runId ?? ""}:${props.workflowId ?? ""}`
  return <StructuredLogViewerBody key={streamKey} {...props} />
}
