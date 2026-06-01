import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { eventToLogEntry } from "@/lib/logLine"
import type { LogLevel } from "@/lib/logLine"
import type { LogRenderEntry } from "@/lib/logLine"

// Event types that produce no meaningful user-facing log line and should be
// filtered out of the rendered output (infrastructure / plumbing events).
// "progress" is shown as compact dim ticks so calibration steps are visible.
const SKIP_EVENT_TYPES = new Set(["workflow_id_ready", "heartbeat"])

// ---------------------------------------------------------------------------
// Render item types (phase separators + event rows)
// ---------------------------------------------------------------------------

type RenderItem =
  | { kind: "phase-sep"; phase: string; label: string; description?: string; key: string }
  | { kind: "event"; ev: ReviewEvent; key: string }

function stableStringify(value: unknown): string {
  if (value == null) return String(value)
  if (typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map((v) => stableStringify(v)).join(",")}]`
  const entries = Object.entries(value as Record<string, unknown>)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`)
  return `{${entries.join(",")}}`
}

function eventStableKey(ev: ReviewEvent): string {
  if (ev.id) return `event-${ev.id}`
  const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""
  const base = `event-${ev.type}-${ts}`
  switch (ev.type) {
    case "phase_start":
    case "phase_done":
      return `${base}-${ev.phase}`
    case "progress":
      return `${base}-${ev.phase}-${ev.current}-${ev.total}`
    case "screening_decision":
      return `${base}-${ev.paper_id}-${ev.stage}-${ev.decision}`
    case "connector_result":
      return `${base}-${ev.name}-${ev.status}-${ev.records}`
    case "api_call":
      return `${base}-${ev.phase}-${ev.call_type}-${ev.paper_id ?? ""}-${ev.section_name ?? ""}-${ev.status}`
    case "status":
      return `${base}-${ev.message}`
    default:
      return `${base}-${stableStringify(ev)}`
  }
}

function buildRenderItems(events: ReviewEvent[]): RenderItem[] {
  const items: RenderItem[] = []
  const keyCounts = new Map<string, number>()

  for (let i = 0; i < events.length; i++) {
    const ev = events[i]
    const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""

    if (SKIP_EVENT_TYPES.has(ev.type)) continue

    const rawKey = eventStableKey(ev)
    const duplicateIndex = keyCounts.get(rawKey) ?? 0
    keyCounts.set(rawKey, duplicateIndex + 1)
    const evKey = duplicateIndex === 0 ? rawKey : `${rawKey}-dup-${duplicateIndex}`

    if (ev.type === "phase_start") {
      const descRaw = (ev as { description?: string }).description
      const desc =
        typeof descRaw === "string" && descRaw.trim().length > 0 ? descRaw.trim() : undefined
      items.push({
        kind: "phase-sep",
        phase: ev.phase,
        label: PHASE_LABELS[ev.phase] ?? ev.phase,
        description: desc,
        key: `sep-${ev.phase}-${evKey}-${ts}`,
      })
      // phase_start is represented by a separator only to avoid duplicate rows.
      continue
    }

    items.push({
      kind: "event",
      ev,
      key: evKey,
    })
  }

  return items
}

// ---------------------------------------------------------------------------
// Row styling per level
// ---------------------------------------------------------------------------

function levelClass(level: LogLevel): string {
  switch (level) {
    case "error":             return "text-intent-danger"
    case "warn":              return "text-intent-warning"
    case "info":              return "text-foreground"
    case "dim":               return "text-muted"
    case "status":            return "text-intent-warning/70 italic"
    // include/exclude/exclude-heuristic handled separately as bordered cards
    default:                  return "text-muted"
  }
}

function screeningCardClass(level: LogLevel): {
  borderClass: string
  badgeClass: string
  textClass: string
} {
  if (level === "include") {
    return {
      borderClass: "border-intent-success bg-intent-success-subtle",
      badgeClass: "text-intent-success",
      textClass: "text-intent-success",
    }
  }
  if (level === "exclude-heuristic") {
    return {
      borderClass: "border-intent-warning-border bg-intent-warning-subtle",
      badgeClass: "text-intent-warning",
      textClass: "text-intent-warning",
    }
  }
  return {
    borderClass: "border-border bg-surface-2/20",
    badgeClass: "text-muted",
    textClass: "text-foreground",
  }
}

function splitTerminalColumns(text: string): { ts: string | null; tag: string | null; message: string } {
  const m = text.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+([A-Z.]+)\s+(.*)$/)
  if (!m) return { ts: null, tag: null, message: text }
  return { ts: m[1], tag: m[2], message: m[3] }
}

// ---------------------------------------------------------------------------
// LogStream
// ---------------------------------------------------------------------------

export interface LogStreamHandle {
  scrollToPhase: (phase: string) => void
}

interface LogStreamProps {
  events: ReviewEvent[]
  /** When false, suppresses auto-scroll to bottom (use when a filter is active). */
  autoScroll?: boolean
}

export const LogStream = forwardRef<LogStreamHandle, LogStreamProps>(function LogStream(
  { events, autoScroll = true },
  ref,
) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)
  const [viewportWidth, setViewportWidth] = useState(0)
  const rowEstimate = 24
  const DEV_PERF_LOG = import.meta.env.DEV

  const renderItems = useMemo(() => buildRenderItems(events), [events])

  const scrollToItemIndex = (index: number) => {
    const container = scrollContainerRef.current
    if (!container) return
    container.scrollTo({
      top: Math.max(0, index * rowEstimate - 8),
      behavior: "smooth",
    })
  }

  useImperativeHandle(ref, () => ({
    scrollToPhase: (phase: string) => {
      const container = scrollContainerRef.current
      const el = container?.querySelector<HTMLElement>(`[data-phase="${phase}"]`)
      if (!container) return
      if (!el) {
        const fallbackIdx = renderItems.findIndex((item) => item.kind === "phase-sep" && item.phase === phase)
        if (fallbackIdx >= 0) {
          scrollToItemIndex(fallbackIdx)
        }
        return
      }
      // getBoundingClientRect gives viewport-relative coords, which correctly
      // accounts for any ancestor transforms/positions. offsetTop would be
      // relative to the nearest positioned ancestor, which may not be the
      // scroll container, producing a wrong offset.
      const elTop = el.getBoundingClientRect().top
      const containerTop = container.getBoundingClientRect().top
      container.scrollTo({
        top: container.scrollTop + (elTop - containerTop) - 8,
        behavior: "smooth",
      })
    },
  }))

  // Watch the sentinel element with an IntersectionObserver so we know whether
  // the user has scrolled away from the bottom.
  useEffect(() => {
    const sentinel = bottomRef.current
    const container = scrollContainerRef.current
    if (!sentinel || !container) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        userScrolledUp.current = !entry.isIntersecting
      },
      { root: container, threshold: 0 },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return
    setViewportHeight(container.clientHeight)
    setViewportWidth(container.clientWidth)
    const onScroll = () => setScrollTop(container.scrollTop)
    container.addEventListener("scroll", onScroll, { passive: true })
    const onResize = () => {
      setViewportHeight(container.clientHeight)
      setViewportWidth(container.clientWidth)
    }
    window.addEventListener("resize", onResize)
    return () => {
      container.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onResize)
    }
  }, [])

  // Scroll to bottom on new events only when the user hasn't scrolled up.
  useEffect(() => {
    if (!autoScroll || userScrolledUp.current) return
    const container = scrollContainerRef.current
    if (!container) return
    container.scrollTo({ top: container.scrollHeight, behavior: "auto" })
  }, [renderItems.length, autoScroll])

  // If auto-scroll was disabled (for search/filter) and gets re-enabled, snap to latest.
  useEffect(() => {
    if (autoScroll && !userScrolledUp.current) {
      const container = scrollContainerRef.current
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: "auto" })
      }
    }
  }, [autoScroll])

  const toggleExpanded = (rowKey: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(rowKey)) next.delete(rowKey)
      else next.add(rowKey)
      return next
    })
  }

  // Enable virtualization based on row count regardless of viewport width.
  // This prevents full DOM mounts during large replay bursts on narrower layouts.
  const virtualEnabled =
    renderItems.length > 350 &&
    expandedRows.size === 0
  const overscan = 40
  const start = virtualEnabled
    ? Math.max(0, Math.floor(scrollTop / rowEstimate) - overscan)
    : 0
  const end = virtualEnabled
    ? Math.min(renderItems.length, Math.ceil((scrollTop + viewportHeight) / rowEstimate) + overscan)
    : renderItems.length
  const visibleItems = renderItems.slice(start, end)
  const topPad = virtualEnabled ? start * rowEstimate : 0
  const bottomPad = virtualEnabled ? (renderItems.length - end) * rowEstimate : 0

  useEffect(() => {
    if (!DEV_PERF_LOG) return
    console.debug("[LogStream render]", {
      events: events.length,
      renderItems: renderItems.length,
      virtualEnabled,
      viewportWidth,
      viewportHeight,
    })
  }, [events.length, renderItems.length, virtualEnabled, viewportWidth, viewportHeight, DEV_PERF_LOG])

  if (events.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-muted bg-card border border-border rounded-xl">
        Events will appear here once the review starts.
      </div>
    )
  }

  return (
    <div
      ref={scrollContainerRef}
      className="h-[clamp(22rem,calc(100dvh-20rem),40rem)] w-full rounded-xl border border-border bg-background overflow-y-auto"
      role="log"
      aria-live="polite"
      aria-label="Event log"
      aria-atomic="false"
    >
      <div className="font-mono text-[11px] flex flex-col p-4 gap-px leading-5">
        {topPad > 0 && <div style={{ height: topPad }} />}
        {visibleItems.map((item) => {
          if (item.kind === "phase-sep") {
            return (
              <div
                key={item.key}
                data-phase={item.phase}
                className={cn(
                  "flex flex-col gap-0.5 mt-3 mb-1 first:mt-0 bg-background/95",
                  virtualEnabled ? "" : "sticky top-0 z-10 backdrop-blur-sm",
                )}
              >
                <div className="flex items-center gap-2">
                  <div className="h-px flex-1 bg-border" />
                  <span className="text-[10px] font-semibold tracking-widest uppercase text-intent-primary/80 shrink-0 px-1">
                    {item.label}
                  </span>
                  <div className="h-px flex-1 bg-border" />
                </div>
                {item.description ? (
                  <div className="text-[10px] text-muted pl-0.5 pr-1 leading-snug">{item.description}</div>
                ) : null}
              </div>
            )
          }

          const { text, level }: LogRenderEntry = eventToLogEntry(item.ev)
          const errorEv = item.kind === "event" && item.ev.type === "error" ? (item.ev as { traceback?: string }) : null

          // Screening decisions get a colored left-border card treatment.
          if (level === "include" || level === "exclude" || level === "exclude-heuristic") {
            const isInclude = level === "include"
            const style = screeningCardClass(level)
            return (
              <div key={item.key} className="flex flex-col gap-0.5">
                <div
                  className={cn(
                    "flex items-baseline gap-2 pl-2 border-l-2 rounded-r py-0.5",
                    style.borderClass,
                  )}
                >
                  {/* Colored INCLUDE / EXCLUDE badge */}
                  <span className={cn(
                    "shrink-0 font-bold text-[10px] tracking-wider uppercase select-none",
                    style.badgeClass,
                  )}>
                    {isInclude ? "INCLUDE" : "EXCLUDE"}
                  </span>
                  {/* Full log line (timestamp + label + conf + reason) */}
                  <span className={cn(
                    "whitespace-pre-wrap break-all min-w-0",
                    style.textClass,
                  )}>
                    {/* Strip the leading "[HH:MM:SS] INCLUDE/EXCLUDE " prefix since the badge shows it */}
                    {text.replace(/^\[\d{2}:\d{2}:\d{2}\] (?:INCLUDE|EXCLUDE)\s+/, "")}
                  </span>
                </div>
              </div>
            )
          }

          // All other event types -- plain text with level-based color
          const cols = splitTerminalColumns(text)
          const canExpand = text.length > 240
          const isExpanded = expandedRows.has(item.key)
          const displayMessage = canExpand && !isExpanded ? `${cols.message.slice(0, 240)}...` : cols.message
          return (
            <div key={item.key} className="flex flex-col gap-1">
              <div className={cn("grid grid-cols-[74px_62px_1fr] items-start gap-x-2", levelClass(level))}>
                <span className="text-muted tabular-nums">{cols.ts ? `[${cols.ts}]` : ""}</span>
                <span className="text-muted">{cols.tag ?? ""}</span>
                <span className="whitespace-pre-wrap break-all min-w-0">
                  {displayMessage}
                  {canExpand && (
                    <>
                      {" "}
                      <button
                        type="button"
                        onClick={() => toggleExpanded(item.key)}
                        className="text-muted hover:text-foreground underline underline-offset-2 transition-colors"
                        title="Toggle full row"
                      >
                        {isExpanded ? "less" : "more"}
                      </button>
                    </>
                  )}
                </span>
              </div>
              {errorEv?.traceback && (
                <pre className="text-[10px] text-muted whitespace-pre-wrap break-all font-mono pl-4 border-l-2 border-intent-danger-border mt-1">
                  {errorEv.traceback}
                </pre>
              )}
            </div>
          )
        })}
        {bottomPad > 0 && <div style={{ height: bottomPad }} />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
})
