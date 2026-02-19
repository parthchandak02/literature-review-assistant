import { useState } from "react"
import { LogStream } from "@/components/LogStream"
import type { ReviewEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

interface LogViewProps {
  events: ReviewEvent[]
}

type Filter = "all" | "phases" | "llm" | "search" | "screening"

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "phases", label: "Phases" },
  { id: "llm", label: "LLM Calls" },
  { id: "search", label: "Search" },
  { id: "screening", label: "Screening" },
]

function filterEvents(events: ReviewEvent[], filter: Filter): ReviewEvent[] {
  if (filter === "all") return events
  if (filter === "phases")
    return events.filter((e) => e.type === "phase_start" || e.type === "phase_done")
  if (filter === "llm") return events.filter((e) => e.type === "api_call")
  if (filter === "search") return events.filter((e) => e.type === "connector_result")
  if (filter === "screening")
    return events.filter((e) => e.type === "screening_decision")
  return events
}

export function LogView({ events }: LogViewProps) {
  const [activeFilter, setActiveFilter] = useState<Filter>("all")
  const filtered = filterEvents(events, activeFilter)

  return (
    <div className="flex flex-col gap-3 max-w-4xl">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setActiveFilter(f.id)}
              className={cn(
                "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                activeFilter === f.id
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-600">{filtered.length} events</span>
      </div>

      <LogStream events={filtered} />
    </div>
  )
}
