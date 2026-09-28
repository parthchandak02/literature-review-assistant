import { useMemo, useRef, useState } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { LogStream } from "@/components/LogStream"
import type { LogStreamHandle } from "@/components/LogStream"
import { FetchError, Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import type { ReviewEvent } from "@/lib/api"
import {
  LOG_SEVERITY_FILTERS,
  filterEventsBySeverity,
  type LogSeverityFilter,
} from "@/lib/logLine"
import { cn } from "@/lib/utils"

export interface ActivityLogPanelProps {
  searchQuery: string
  onSearchQueryChange: (query: string) => void
  effectiveLoadingHistory: boolean
  eventCountLabel: string | null
  fetchError: string | null
  filteredEvents: ReviewEvent[]
  runId: string
  workflowId?: string | null
  onRetryHistorical: (runId: string, workflowId: string | null | undefined) => void
}

const EMPTY_FILTER_COPY: Record<Exclude<LogSeverityFilter, "all">, string> = {
  warnings: "No warnings or errors",
  errors: "No errors",
  decisions: "No screening decisions",
}

export function ActivityLogPanel({
  searchQuery,
  onSearchQueryChange,
  effectiveLoadingHistory,
  eventCountLabel,
  fetchError,
  filteredEvents,
  runId,
  workflowId,
  onRetryHistorical,
}: ActivityLogPanelProps) {
  const logRef = useRef<LogStreamHandle>(null)
  const [severity, setSeverity] = useState<LogSeverityFilter>("all")
  const query = searchQuery.trim()

  const visibleEvents = useMemo(
    () => filterEventsBySeverity(filteredEvents, severity),
    [filteredEvents, severity],
  )
  const matchCount = useMemo(
    () => (severity === "all" ? visibleEvents.length : visibleEvents.filter((ev) => ev.type !== "phase_start").length),
    [visibleEvents, severity],
  )
  const countLabel =
    severity === "all" || effectiveLoadingHistory ? eventCountLabel : `${matchCount} of ${filteredEvents.length} events`

  function renderEmpty() {
    if (query) {
      return (
        <>
          <p className="text-muted text-sm">No events match &lsquo;{query}&rsquo;</p>
          <Button type="button" size="sm" variant="outline" onClick={() => onSearchQueryChange("")}>
            Clear search
          </Button>
        </>
      )
    }
    if (severity !== "all" && filteredEvents.length > 0) {
      return (
        <>
          <p className="text-muted text-sm">{EMPTY_FILTER_COPY[severity]} yet.</p>
          <Button type="button" size="sm" variant="outline" onClick={() => setSeverity("all")}>
            Show all events
          </Button>
        </>
      )
    }
    return <p className="text-muted text-sm">Events will appear here once the review starts.</p>
  }

  const isEmpty = severity === "all" ? filteredEvents.length === 0 : matchCount === 0

  return (
    <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
      <ViewToolbar className="overflow-hidden flex-wrap gap-2">
        <span className="label-caps shrink-0">Activity Log</span>

        {effectiveLoadingHistory ? (
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <Spinner size="sm" />
            Loading...
          </span>
        ) : countLabel ? (
          <span className="text-xs text-muted tabular-nums shrink-0">{countLabel}</span>
        ) : null}

        <div role="group" aria-label="Filter by severity" className="flex items-center gap-1 shrink-0">
          {LOG_SEVERITY_FILTERS.map((f) => {
            const active = severity === f.id
            return (
              <button
                key={f.id}
                type="button"
                aria-pressed={active}
                onClick={() => setSeverity(f.id)}
                className={cn(
                  "rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors motion-reduce:transition-none",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
                  active
                    ? "border-intent-primary-border bg-intent-primary-subtle text-foreground"
                    : "border-border text-muted hover:text-foreground hover:bg-surface-2/60",
                )}
              >
                {f.label}
              </button>
            )
          })}
        </div>

        <div className="relative flex-1 min-w-[10rem]">
          <Search
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted pointer-events-none"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search activity log"
            placeholder="Search log..."
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            className="pl-8 h-7 text-xs bg-transparent border-border w-full"
          />
        </div>
      </ViewToolbar>

      <div className="data-surface flex-1 overflow-y-auto min-h-0">
        {fetchError && (
          <div className="p-4">
            <FetchError
              message={fetchError}
              onRetry={runId ? () => onRetryHistorical(runId, workflowId) : undefined}
            />
          </div>
        )}

        {!effectiveLoadingHistory && isEmpty && !fetchError && (
          <div className="py-12 flex flex-col items-center justify-center gap-3 text-center">{renderEmpty()}</div>
        )}

        {!isEmpty && (
          <LogStream ref={logRef} events={visibleEvents} autoScroll={!query} />
        )}
      </div>
    </div>
  )
}
