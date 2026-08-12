import { useQuery, type QueryFunctionContext } from "@tanstack/react-query"
import { fetchHistoryRail, railEntryToHistoryEntry } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import { HISTORY_REFRESH_MS, resolveHistoryRefetchInterval } from "@/lib/pollingBackoff"

export { HISTORY_REFRESH_MS, resolveHistoryRefetchInterval }

export function historyQueryKey(runRoot = "runs") {
  return ["history", runRoot] as const
}

/** Carry forward rail stats from a prior full fetch when polling with stats=false. */
export function mergeHistoryStats(
  fresh: HistoryEntry[],
  previous: HistoryEntry[],
): HistoryEntry[] {
  const prevById = new Map(previous.map((entry) => [entry.workflow_id, entry]))
  return fresh.map((entry) => {
    const prev = prevById.get(entry.workflow_id)
    if (!prev) return entry
    return {
      ...entry,
      papers_found: prev.papers_found,
      papers_included: prev.papers_included,
      total_cost: prev.total_cost,
      stats_ok: prev.stats_ok,
    }
  })
}

export async function fetchSidebarHistory(
  runRoot = "runs",
  options?: { stats?: boolean; previous?: HistoryEntry[] },
): Promise<HistoryEntry[]> {
  const stats = options?.stats ?? true
  const rail = await fetchHistoryRail({ runRoot, stats })
  const entries = rail.map(railEntryToHistoryEntry)
  if (!stats && options?.previous != null) {
    return mergeHistoryStats(entries, options.previous)
  }
  return entries
}

export function createHistoryQueryFn(runRoot = "runs") {
  return async ({
    client,
  }: QueryFunctionContext<ReturnType<typeof historyQueryKey>>) => {
    const key = historyQueryKey(runRoot)
    const previous = client.getQueryData<HistoryEntry[]>(key)
    const stats = previous == null
    return fetchSidebarHistory(runRoot, {
      stats,
      previous: previous ?? undefined,
    })
  }
}

export function useHistory(options?: { enabled?: boolean; refetchInterval?: number | false }) {
  return useQuery({
    queryKey: historyQueryKey(),
    queryFn: createHistoryQueryFn(),
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval ?? HISTORY_REFRESH_MS,
    refetchIntervalInBackground: false,
  })
}

export function historyFetchErrorMessage(error: unknown): string | null {
  const msg = error instanceof Error ? error.message : String(error)
  return msg.toLowerCase().includes("fetch") ? "Cannot reach backend" : msg
}
