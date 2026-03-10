import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { eventToLogEntry } from "@/lib/logLine"
import type { ActivityLogMode } from "@/lib/logLine"
import type { LogLevel } from "@/lib/logLine"
import type { LogRenderEntry } from "@/lib/logLine"

// Event types that produce no meaningful user-facing log line and should be
// filtered out of the rendered output (infrastructure / plumbing events).
// "progress" is shown as compact dim ticks so calibration steps are visible.
const SKIP_EVENT_TYPES = new Set(["workflow_id_ready", "heartbeat"])

// ---------------------------------------------------------------------------
// Render item types (phase separators + event rows)
// ---------------------------------------------------------------------------

export type RenderItem =
  | { kind: "phase-sep"; phase: string; label: string; key: string }
  | { kind: "event"; ev: ReviewEvent; entry: LogRenderEntry; key: string }
  | { kind: "summary"; entry: LogRenderEntry; key: string }

export function buildRenderItems(events: ReviewEvent[], mode: ActivityLogMode): RenderItem[] {
  const eventPriority: Record<string, number> = {
    phase_start: 1,
    status: 2,
    progress: 3,
    screening_decision: 4,
    phase_done: 5,
    done: 6,
    error: 7,
    cancelled: 8,
  }

  const _parseBatchIdx = (ev: ReviewEvent): number | null => {
    if (ev.type !== "status") return null
    const m = (ev.message ?? "").match(/Pre-ranker batch\s+(\d+)\//i)
    return m ? Number(m[1]) : null
  }

  // Keep source order by default, but for same-timestamp pre-ranker status rows
  // use batch index ordering so concurrent completions render deterministically.
  const ordered = events
    .map((ev, i) => ({ ev, i }))
    .sort((a, b) => {
      const aTs = "ts" in a.ev ? (a.ev.ts ?? "") : ""
      const bTs = "ts" in b.ev ? (b.ev.ts ?? "") : ""
      if (aTs === bTs) {
        const aBatch = _parseBatchIdx(a.ev)
        const bBatch = _parseBatchIdx(b.ev)
        if (aBatch != null && bBatch != null && aBatch !== bBatch) {
          return aBatch - bBatch
        }
        const aRank = eventPriority[a.ev.type] ?? 100
        const bRank = eventPriority[b.ev.type] ?? 100
        if (aRank !== bRank) {
          return aRank - bRank
        }
      }
      return a.i - b.i
    })
    .map((x) => x.ev)

  const items: RenderItem[] = []
  const userPhaseCounters: Record<string, {
    llmCalls: number
    include: number
    exclude: number
    pdfOk: number
    pdfFail: number
  }> = {}

  for (let i = 0; i < ordered.length; i++) {
    const ev = ordered[i]
    const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""
    const phaseKey = (() => {
      if (ev.type === "api_call" || ev.type === "progress" || ev.type === "phase_done" || ev.type === "phase_start") {
        return (ev as { phase?: string }).phase ?? "unknown"
      }
      if (ev.type === "screening_decision" || ev.type === "pdf_result" || ev.type === "screening_prefilter_done" || ev.type === "batch_screen_done") {
        return "phase_3_screening"
      }
      return "unknown"
    })()
    if (!userPhaseCounters[phaseKey]) {
      userPhaseCounters[phaseKey] = { llmCalls: 0, include: 0, exclude: 0, pdfOk: 0, pdfFail: 0 }
    }

    if (SKIP_EVENT_TYPES.has(ev.type)) continue

    if (ev.type === "phase_start") {
      items.push({
        kind: "phase-sep",
        phase: ev.phase,
        label: PHASE_LABELS[ev.phase] ?? ev.phase,
        key: `sep-${ev.phase}-${ts}-${i}`,
      })
      // phase_start is represented by a separator only to avoid duplicate rows.
      continue
    }

    if (mode === "user") {
      if (ev.type === "api_call") {
        userPhaseCounters[phaseKey].llmCalls += 1
        continue
      }
      if (ev.type === "progress") {
        continue
      }
      if (ev.type === "screening_decision") {
        if (ev.decision === "include") userPhaseCounters[phaseKey].include += 1
        else userPhaseCounters[phaseKey].exclude += 1
        continue
      }
      if (ev.type === "pdf_result") {
        if (ev.success) userPhaseCounters[phaseKey].pdfOk += 1
        else userPhaseCounters[phaseKey].pdfFail += 1
        continue
      }
      if (ev.type === "phase_done") {
        const counts = userPhaseCounters[phaseKey]
        if (counts && (counts.llmCalls > 0 || counts.include > 0 || counts.exclude > 0 || counts.pdfOk > 0 || counts.pdfFail > 0)) {
          const bits: string[] = []
          if (counts.llmCalls > 0) bits.push(`LLM calls=${counts.llmCalls}`)
          if (counts.include > 0 || counts.exclude > 0) bits.push(`decisions include=${counts.include}, exclude=${counts.exclude}`)
          if (counts.pdfOk > 0 || counts.pdfFail > 0) bits.push(`PDF ok=${counts.pdfOk}, unavailable=${counts.pdfFail}`)
          items.push({
            kind: "summary",
            key: `summary-${phaseKey}-${ts}-${i}`,
            entry: {
              text: `[${ts ? ts.slice(11, 19) : "--:--:--"}] SUMMARY ${bits.join(" | ")}`,
              level: "status",
              severity: "status",
              kind: "status",
              phase: phaseKey,
              eventType: "status",
              compactable: false,
              groupKey: `summary:${phaseKey}`,
              isResumeRelated: false,
              isResumeNoOp: false,
            },
          })
        }
      }
    }

    items.push({
      kind: "event",
      ev,
      entry: eventToLogEntry(ev, mode),
      key: `${ev.type}-${ts}-${i}`,
    })
  }

  return items
}

// ---------------------------------------------------------------------------
// Row styling per level
// ---------------------------------------------------------------------------

function levelClass(level: LogLevel): string {
  switch (level) {
    case "error":             return "text-red-400"
    case "warn":              return "text-amber-400"
    case "info":              return "text-zinc-200"
    case "dim":               return "text-zinc-600"
    case "status":            return "text-amber-500/70 italic"
    // include/exclude/exclude-heuristic handled separately as bordered cards
    default:                  return "text-zinc-600"
  }
}

function screeningCardClass(level: LogLevel): {
  borderClass: string
  badgeClass: string
  textClass: string
} {
  if (level === "include") {
    return {
      borderClass: "border-emerald-500 bg-emerald-500/5",
      badgeClass: "text-emerald-400",
      textClass: "text-emerald-300",
    }
  }
  if (level === "exclude-heuristic") {
    return {
      borderClass: "border-amber-700/60 bg-amber-600/5",
      badgeClass: "text-amber-500",
      textClass: "text-amber-300/90",
    }
  }
  return {
    borderClass: "border-zinc-600 bg-zinc-800/20",
    badgeClass: "text-zinc-400",
    textClass: "text-zinc-300",
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
  mode: ActivityLogMode
}

export const LogStream = forwardRef<LogStreamHandle, LogStreamProps>(function LogStream(
  { events, autoScroll = true, mode },
  ref,
) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const userScrolledUp = useRef(false)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)
  const rowEstimate = 24

  const renderItems = useMemo(() => buildRenderItems(events, mode), [events, mode])

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
    const onScroll = () => setScrollTop(container.scrollTop)
    container.addEventListener("scroll", onScroll, { passive: true })
    const onResize = () => setViewportHeight(container.clientHeight)
    window.addEventListener("resize", onResize)
    return () => {
      container.removeEventListener("scroll", onScroll)
      window.removeEventListener("resize", onResize)
    }
  }, [])

  // Scroll to bottom on new events only when the user hasn't scrolled up.
  useEffect(() => {
    if (autoScroll && !userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [events.length, autoScroll])

  const toggleExpanded = (rowKey: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(rowKey)) next.delete(rowKey)
      else next.add(rowKey)
      return next
    })
  }

  if (events.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-zinc-600 bg-zinc-900 border border-zinc-800 rounded-xl">
        Events will appear here once the review starts.
      </div>
    )
  }

  const virtualEnabled = renderItems.length > 500
  const overscan = 100
  const start = virtualEnabled
    ? Math.max(0, Math.floor(scrollTop / rowEstimate) - overscan)
    : 0
  const end = virtualEnabled
    ? Math.min(renderItems.length, Math.ceil((scrollTop + viewportHeight) / rowEstimate) + overscan)
    : renderItems.length
  const visibleItems = renderItems.slice(start, end)
  const topPad = virtualEnabled ? start * rowEstimate : 0
  const bottomPad = virtualEnabled ? (renderItems.length - end) * rowEstimate : 0

  return (
    <div
      ref={scrollContainerRef}
      className="h-[32rem] w-full rounded-xl border border-zinc-800 bg-background overflow-y-auto"
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
                className="flex items-center gap-2 mt-3 mb-1 first:mt-0 sticky top-0 z-10 bg-background/95 backdrop-blur-sm"
              >
                <div className="h-px flex-1 bg-zinc-800" />
                <span className="text-[10px] font-semibold tracking-widest uppercase text-violet-500/80 shrink-0 px-1">
                  {item.label}
                </span>
                <div className="h-px flex-1 bg-zinc-800" />
              </div>
            )
          }

          const { text, level } = item.entry
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
                <span className="text-zinc-500 tabular-nums">{cols.ts ? `[${cols.ts}]` : ""}</span>
                <span className="text-zinc-400">{cols.tag ?? ""}</span>
                <span className="whitespace-pre-wrap break-all min-w-0">
                  {displayMessage}
                  {canExpand && (
                    <>
                      {" "}
                      <button
                        type="button"
                        onClick={() => toggleExpanded(item.key)}
                        className="text-zinc-500 hover:text-zinc-300 underline underline-offset-2 transition-colors"
                        title="Toggle full row"
                      >
                        {isExpanded ? "less" : "more"}
                      </button>
                    </>
                  )}
                </span>
              </div>
              {errorEv?.traceback && (
                <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap break-all font-mono pl-4 border-l-2 border-red-500/30 mt-1">
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
