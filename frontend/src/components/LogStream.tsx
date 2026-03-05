import { useEffect, useMemo, useRef } from "react"
import { cn } from "@/lib/utils"
import { PHASE_LABELS } from "@/lib/constants"
import type { ReviewEvent } from "@/lib/api"
import { eventToLogLine } from "@/lib/logLine"

// Event types that produce no meaningful user-facing log line and should be
// filtered out of the rendered output (infrastructure / plumbing events).
const SKIP_EVENT_TYPES = new Set(["workflow_id_ready", "heartbeat"])

// ---------------------------------------------------------------------------
// Render item types (phase separators + LLM grouping)
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
// LogStream
// ---------------------------------------------------------------------------

interface LogStreamProps {
  events: ReviewEvent[]
  /** When false, suppresses auto-scroll to bottom (use when a filter is active). */
  autoScroll?: boolean
}

export function LogStream({ events, autoScroll = true }: LogStreamProps) {
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // True when the user has manually scrolled up so we suppress auto-scroll.
  const userScrolledUp = useRef(false)

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
          return (
            <div key={item.key} className="flex flex-col gap-1">
              <div
                className={cn(
                  "whitespace-pre-wrap break-all",
                  level === "error" && "text-red-400",
                  level === "warn" && "text-amber-400",
                  level === "info" && "text-zinc-200",
                  level === "dim" && "text-zinc-600",
                )}
              >
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
}
