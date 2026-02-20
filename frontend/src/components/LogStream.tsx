import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { ReviewEvent } from "@/lib/api"

// ---------------------------------------------------------------------------
// Event -> log line conversion
// ---------------------------------------------------------------------------

function eventToLogLine(ev: ReviewEvent): { text: string; level: "info" | "warn" | "error" | "dim" } {
  switch (ev.type) {
    case "phase_start":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] PHASE  ${ev.phase}${ev.description ? "  " + ev.description : ""}`,
        level: "info",
      }
    case "phase_done":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] DONE   ${ev.phase}`, level: "info" }
    case "progress":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] PROG   ${ev.phase}: ${ev.current}/${ev.total}`, level: "dim" }
    case "api_call":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] LLM    ${ev.status.toUpperCase().padEnd(7)} ${ev.source} | ${ev.call_type}${ev.model ? " | " + ev.model.split(":").pop() : ""}${ev.latency_ms != null ? " | " + ev.latency_ms + "ms" : ""}${ev.cost_usd != null && ev.cost_usd > 0 ? " | $" + ev.cost_usd.toFixed(4) : ""}`,
        level: ev.status === "success" ? "dim" : "error",
      }
    case "connector_result":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] SEARCH ${ev.status === "success" ? "OK     " : "FAIL   "} ${ev.name}: ${ev.status === "success" ? ev.records + " records" : (ev.error ?? "unknown error")}`,
        level: ev.status === "success" ? "dim" : "warn",
      }
    case "screening_decision":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] SCREEN ${String(ev.decision).toUpperCase().padEnd(7)} ${ev.stage} | ${ev.paper_id?.slice(0, 16) ?? ""}`,
        level: ev.decision === "include" ? "info" : "dim",
      }
    case "extraction_paper":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] EXTRACT        ${ev.paper_id?.slice(0, 16) ?? ""} design=${ev.design} rob=${ev.rob_judgment}`,
        level: "dim",
      }
    case "synthesis":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] SYNTH  feasible=${ev.feasible} groups=${ev.groups} n=${ev.n_studies}`,
        level: "info",
      }
    case "rate_limit_wait":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] RATELIMIT ${ev.tier}: ${ev.slots_used}/${ev.limit} -- waiting`,
        level: "warn",
      }
    case "db_ready":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] DB     ready  database explorer unlocked`,
        level: "dim",
      }
    case "done":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? "--:--:--"}] DONE   Review complete.`,
        level: "info",
      }
    case "error":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? "--:--:--"}] ERROR  ${ev.msg}`,
        level: "error",
      }
    case "cancelled":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? "--:--:--"}] CANCEL Review cancelled.`,
        level: "warn",
      }
    default:
      return { text: JSON.stringify(ev), level: "dim" }
  }
}

// ---------------------------------------------------------------------------
// Render item types (phase separators + LLM grouping)
// ---------------------------------------------------------------------------

const PHASE_LABELS: Record<string, string> = {
  phase_2_search: "Search",
  phase_3_screening: "Screening",
  phase_4_extraction_quality: "Extraction & Quality",
  phase_5_synthesis: "Synthesis",
  phase_6_writing: "Writing",
  finalize: "Finalize",
}

type RenderItem =
  | { kind: "phase-sep"; phase: string; label: string; key: string }
  | { kind: "llm-group"; count: number; totalCost: number; firstTs: string; phase: string; key: string }
  | { kind: "event"; ev: ReviewEvent; key: string }

const LLM_GROUP_THRESHOLD = 3

function buildRenderItems(events: ReviewEvent[]): RenderItem[] {
  const items: RenderItem[] = []
  let i = 0

  while (i < events.length) {
    const ev = events[i]
    const ts = "ts" in ev ? (ev as { ts?: string }).ts ?? "" : ""

    // Inject a visual phase separator before every phase_start event.
    if (ev.type === "phase_start") {
      items.push({
        kind: "phase-sep",
        phase: ev.phase,
        label: PHASE_LABELS[ev.phase] ?? ev.phase,
        key: `sep-${ev.phase}-${ts}-${i}`,
      })
      items.push({ kind: "event", ev, key: `${ev.type}-${ts}-${i}` })
      i++
      continue
    }

    // Collapse runs of 3+ consecutive api_call events into a summary row.
    if (ev.type === "api_call") {
      let j = i
      while (j < events.length && events[j].type === "api_call") {
        j++
      }
      const runLen = j - i
      if (runLen >= LLM_GROUP_THRESHOLD) {
        const group = events.slice(i, j) as Array<ReviewEvent & { type: "api_call" }>
        const totalCost = group.reduce((acc, e) => acc + (e.cost_usd ?? 0), 0)
        const firstTs = (group[0] as { ts?: string }).ts ?? ""
        const phase = group[0].phase
        items.push({
          kind: "llm-group",
          count: runLen,
          totalCost,
          firstTs,
          phase,
          key: `llm-group-${firstTs}-${i}`,
        })
        i = j
        continue
      }
    }

    items.push({ kind: "event", ev, key: `${ev.type}-${ts}-${i}` })
    i++
  }

  return items
}

// ---------------------------------------------------------------------------
// LogStream
// ---------------------------------------------------------------------------

interface LogStreamProps {
  events: ReviewEvent[]
}

export function LogStream({ events }: LogStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events.length])

  if (events.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center text-sm text-zinc-600 bg-zinc-900 border border-zinc-800 rounded-xl">
        Events will appear here once the review starts.
      </div>
    )
  }

  const renderItems = buildRenderItems(events)

  return (
    <ScrollArea
      className="h-[520px] w-full rounded-xl border border-zinc-800 bg-[#0d0d0f]"
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

          if (item.kind === "llm-group") {
            const costStr = item.totalCost > 0 ? ` | $${item.totalCost.toFixed(4)} total` : ""
            return (
              <div key={item.key} className="text-zinc-700 italic">
                {`[${item.firstTs.slice(11, 19) ?? ""}] LLM    ... ${item.count} calls${costStr}`}
              </div>
            )
          }

          const { text, level } = eventToLogLine(item.ev)
          return (
            <div
              key={item.key}
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
          )
        })}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
