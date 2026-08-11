import { useRef } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { LogStream } from "@/components/LogStream"
import type { LogStreamHandle } from "@/components/LogStream"
import { FetchError, Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import type { ReviewEvent } from "@/lib/api"

export interface ActivityLogPanelProps {
  searchQuery: string
  onSearchQueryChange: (query: string) => void
  effectiveLoadingHistory: boolean
  eventCountLabel: string | null
  fetchError: string | null
  filteredEvents: ReviewEvent[]
  runId: string
  workflowId?: string | null
  attachPending: boolean
  onRetryHistorical: (runId: string, workflowId: string | null | undefined, attachPending: boolean) => void
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
  attachPending,
  onRetryHistorical,
}: ActivityLogPanelProps) {
  const logRef = useRef<LogStreamHandle>(null)

  return (
    <div className="card-surface overflow-hidden flex flex-col flex-1 min-h-0">
      <ViewToolbar className="overflow-hidden gap-2">
        <span className="label-caps shrink-0">Activity Log</span>

        {effectiveLoadingHistory ? (
          <span className="flex items-center gap-1.5 text-xs text-muted">
            <Spinner size="sm" />
            Loading...
          </span>
        ) : eventCountLabel ? (
          <span className="text-xs text-muted tabular-nums shrink-0">
            {eventCountLabel}
          </span>
        ) : null}

        <div className="relative flex-1 min-w-0">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted pointer-events-none" />
          <Input
            type="text"
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
              onRetry={
                runId
                  ? () => onRetryHistorical(runId, workflowId, attachPending)
                  : undefined
              }
            />
          </div>
        )}

        {!effectiveLoadingHistory && filteredEvents.length === 0 && !fetchError && (
          <div className="py-12 flex items-center justify-center">
            <p className="text-muted text-sm">
              Events will appear here once the review starts.
            </p>
          </div>
        )}

        {filteredEvents.length > 0 && (
          <LogStream ref={logRef} events={filteredEvents} autoScroll={!searchQuery.trim()} />
        )}
      </div>
    </div>
  )
}
