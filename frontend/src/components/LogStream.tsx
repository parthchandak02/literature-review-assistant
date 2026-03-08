import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react"
import { cn } from "@/lib/utils"
import { PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { eventToLogLine } from "@/lib/logLine"
import type { LogLevel } from "@/lib/logLine"

// Event types that produce no meaningful user-facing log line and should be
// filtered out of the rendered output (infrastructure / plumbing events).
// "progress" is shown as compact dim ticks so calibration steps are visible.
const SKIP_EVENT_TYPES = new Set(["workflow_id_ready", "heartbeat"])

// ---------------------------------------------------------------------------
// Render item types (phase separators + event rows)
// ---------------------------------------------------------------------------

type RenderItem =
  | { kind: "phase-sep"; phase: string; label: string; key: string }
  | { kind: "event"; ev: ReviewEvent; key: string }

function buildRenderItems(events: ReviewEvent[]): RenderItem[] {
  const items: RenderItem[] = []

  for (let i = 0; i < events.length; i++) {
    const ev = events[i]
    const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""

    if (SKIP_EVENT_TYPES.has(ev.type)) continue

    if (ev.type === "phase_start") {
      items.push({
        kind: "phase-sep",
        phase: ev.phase,
        label: PHASE_LABELS[ev.phase] ?? ev.phase,
        key: `sep-${ev.phase}-${ts}-${i}`,
      })
    }

    items.push({ kind: "event", ev, key: `${ev.type}-${ts}-${i}` })
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

  useImperativeHandle(ref, () => ({
    scrollToPhase: (phase: string) => {
      const container = scrollContainerRef.current
      const el = container?.querySelector<HTMLElement>(`[data-phase="${phase}"]`)
      if (!el || !container) return
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

  // Scroll to bottom on new events only when the user hasn't scrolled up.
  useEffect(() => {
    if (autoScroll && !userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [events.length, autoScroll])

  const renderItems = useMemo(() => buildRenderItems(events), [events])

  if (events.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-zinc-600 bg-zinc-900 border border-zinc-800 rounded-xl">
        Events will appear here once the review starts.
      </div>
    )
  }

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
        {renderItems.map((item) => {
          if (item.kind === "phase-sep") {
            return (
              <div
                key={item.key}
                data-phase={item.phase}
                className="flex items-center gap-2 mt-3 mb-1 first:mt-0"
              >
                <div className="h-px flex-1 bg-zinc-800" />
                <span className="text-[10px] font-semibold tracking-widest uppercase text-violet-500/80 shrink-0 px-1">
                  {item.label}
                </span>
                <div className="h-px flex-1 bg-zinc-800" />
              </div>
            )
          }

          const { text, level } = eventToLogLine(item.ev)
          const errorEv = item.ev.type === "error" ? (item.ev as { traceback?: string }) : null

          // Progress ticks -- compact dim dots shown during calibration (1/15, 2/15...)
          if (item.ev.type === "progress") {
            return (
              <div key={item.key} className="text-zinc-700 text-[10px] leading-4">
                {text.replace(/^\[\d{2}:\d{2}:\d{2}\] PROG\s+/, "")}
              </div>
            )
          }

          // Screening decisions get a colored left-border card treatment.
          if (level === "include" || level === "exclude" || level === "exclude-heuristic") {
            const isInclude = level === "include"
            const isHeuristic = level === "exclude-heuristic"
            return (
              <div key={item.key} className="flex flex-col gap-0.5">
                <div
                  className={cn(
                    "flex items-baseline gap-2 pl-2 border-l-2 rounded-r py-0.5",
                    isInclude
                      ? "border-emerald-500 bg-emerald-500/5"
                      : isHeuristic
                        ? "border-amber-800/50"
                        : "border-zinc-700",
                  )}
                >
                  {/* Colored INCLUDE / EXCLUDE badge */}
                  <span className={cn(
                    "shrink-0 font-bold text-[10px] tracking-wider uppercase select-none",
                    isInclude ? "text-emerald-400" : isHeuristic ? "text-amber-700" : "text-zinc-600",
                  )}>
                    {isInclude ? "INCLUDE" : "EXCLUDE"}
                  </span>
                  {/* Full log line (timestamp + label + conf + reason) */}
                  <span className={cn(
                    "whitespace-pre-wrap break-all min-w-0",
                    isInclude ? "text-emerald-300" : isHeuristic ? "text-amber-800/80" : "text-zinc-500",
                  )}>
                    {/* Strip the leading "[HH:MM:SS] INCLUDE/EXCLUDE " prefix since the badge shows it */}
                    {text.replace(/^\[\d{2}:\d{2}:\d{2}\] (?:INCLUDE|EXCLUDE)\s+/, "")}
                  </span>
                </div>
              </div>
            )
          }

          // Status events ("..." amber working indicator)
          if (level === "status") {
            return (
              <div key={item.key} className="flex items-center gap-1.5 text-amber-500/60 italic">
                <span className="shrink-0 text-amber-500/40">...</span>
                <span className="whitespace-pre-wrap break-all">
                  {/* Strip "[HH:MM:SS] ...    " prefix -- just show the message */}
                  {text.replace(/^\[\d{2}:\d{2}:\d{2}\] \.{3}\s+/, "")}
                </span>
              </div>
            )
          }

          // All other event types -- plain text with level-based color
          return (
            <div key={item.key} className="flex flex-col gap-1">
              <div className={cn("whitespace-pre-wrap break-all", levelClass(level))}>
                {text}
              </div>
              {errorEv?.traceback && (
                <pre className="text-[10px] text-zinc-500 whitespace-pre-wrap break-all font-mono pl-4 border-l-2 border-red-500/30 mt-1">
                  {errorEv.traceback}
                </pre>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
})
