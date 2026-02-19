import { useEffect, useRef } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { ReviewEvent } from "@/lib/api"

function eventToLogLine(ev: ReviewEvent): { text: string; level: "info" | "warn" | "error" | "dim" } {
  switch (ev.type) {
    case "phase_start":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] Phase started: ${ev.phase}${ev.description ? " -- " + ev.description : ""}`, level: "info" }
    case "phase_done":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] Phase done: ${ev.phase}`, level: "info" }
    case "progress":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] ${ev.phase}: ${ev.current}/${ev.total}`, level: "dim" }
    case "api_call":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] LLM ${ev.status}: ${ev.source} | ${ev.call_type}${ev.model ? " | " + ev.model.split(":").pop() : ""}${ev.latency_ms != null ? " | " + ev.latency_ms + "ms" : ""}${ev.cost_usd != null && ev.cost_usd > 0 ? " | $" + ev.cost_usd.toFixed(4) : ""}`,
        level: ev.status === "success" ? "dim" : "error",
      }
    case "connector_result":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] ${ev.name}: ${ev.status === "success" ? ev.records + " records" : "FAILED " + (ev.error ?? "")}`,
        level: ev.status === "success" ? "dim" : "warn",
      }
    case "screening_decision":
      return {
        text: `[${ev.ts?.slice(11, 19) ?? ""}] ${ev.stage} | ${ev.paper_id?.slice(0, 12) ?? ""} -> ${ev.decision}`,
        level: ev.decision === "include" ? "info" : "dim",
      }
    case "extraction_paper":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] Extracted: ${ev.paper_id?.slice(0, 12) ?? ""} design=${ev.design} rob=${ev.rob_judgment}`, level: "dim" }
    case "synthesis":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] Synthesis: feasible=${ev.feasible} groups=${ev.groups} n=${ev.n_studies}`, level: "info" }
    case "rate_limit_wait":
      return { text: `[${ev.ts?.slice(11, 19) ?? ""}] Rate limit (${ev.tier}): ${ev.slots_used}/${ev.limit} -- waiting`, level: "warn" }
    case "done":
      return { text: "Review complete.", level: "info" }
    case "error":
      return { text: `ERROR: ${ev.msg}`, level: "error" }
    case "cancelled":
      return { text: "Review cancelled.", level: "warn" }
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
      <div className="h-64 flex items-center justify-center text-sm text-muted-foreground">
        Events will appear here once the review starts.
      </div>
    )
  }

  return (
    <ScrollArea className="h-80 w-full rounded-md border bg-muted/20 p-1">
      <div className="font-mono text-xs flex flex-col gap-0.5 p-3">
        {events.map((ev, i) => {
          const { text, level } = eventToLogLine(ev)
          return (
            <div
              key={i}
              className={cn(
                "leading-5",
                level === "error" && "text-destructive font-medium",
                level === "warn" && "text-yellow-600 dark:text-yellow-400",
                level === "info" && "text-foreground",
                level === "dim" && "text-muted-foreground",
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
