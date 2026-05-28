import { useQuery } from "@tanstack/react-query"
import { fetchHistoricalReviewEvents } from "@/lib/api"
import type { ReviewEvent } from "@/lib/api"

export function historicalEventsQueryKey(
  workflowId: string | null | undefined,
  runId: string,
  attachPending?: boolean,
) {
  return ["historicalEvents", workflowId ?? "", runId, attachPending ?? false] as const
}

export function useHistoricalEvents(
  workflowId: string | null | undefined,
  runId: string,
  options?: { enabled?: boolean; attachPending?: boolean },
) {
  const enabled = options?.enabled ?? true
  return useQuery({
    queryKey: historicalEventsQueryKey(workflowId, runId, options?.attachPending),
    queryFn: () =>
      fetchHistoricalReviewEvents(workflowId, runId, {
        attachPending: options?.attachPending,
      }),
    enabled: enabled && Boolean(runId),
    staleTime: 30_000,
  })
}

export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; error: Error }
  | { status: "empty" }
  | { status: "success"; data: T }

export function queryToAsyncState<T>(
  query: { isPending: boolean; isError: boolean; error: Error | null; data: T | undefined },
  isEmpty?: (data: T) => boolean,
): AsyncState<T> {
  if (query.isPending) return { status: "loading" }
  if (query.isError && query.error) return { status: "error", error: query.error }
  if (query.data === undefined) return { status: "idle" }
  if (isEmpty?.(query.data)) return { status: "empty" }
  return { status: "success", data: query.data }
}

export type { ReviewEvent }
