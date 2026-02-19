import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { ReviewEvent } from "@/lib/api"

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
    case "done":
      return { text: "[--:--:--] DONE   Review complete.", level: "info" }
    case "error":
      return { text: `[--:--:--] ERROR  ${ev.msg}`, level: "error" }
    case "cancelled":
      return { text: "[--:--:--] CANCEL Review cancelled.", level: "warn" }
    default:
      return { text: JSON.stringify(ev), level: "dim" }
  }
}

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

  return (
    <ScrollArea className="h-[520px] w-full rounded-xl border border-zinc-800 bg-[#0d0d0f]">
      <div className="font-mono text-[11px] flex flex-col p-4 gap-px leading-5">
        {events.map((ev, i) => {
          const { text, level } = eventToLogLine(ev)
          return (
            <div
              key={i}
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
