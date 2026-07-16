import { useQuery } from "@tanstack/react-query"
import {
  fetchDbTables,
  fetchPapersAll,
  fetchPapersFacets,
  fetchPapersSuggest,
} from "@/lib/api"

export const LIVE_DB_REFRESH_MS = 10_000

export interface DbPapersFilters {
  titleFilter: string
  authorFilter: string
  taFilter: string
  ftFilter: string
  primaryStatusFilter: string
  yearFilter: string
  sourceFilter: string
  countryFilter: string
}

export function dbPapersQueryKey(
  runId: string,
  filters: DbPapersFilters,
  page: number,
  pageSize: number,
) {
  return ["dbPapers", runId, filters, page, pageSize] as const
}

export function dbPapersFacetsQueryKey(runId: string) {
  return ["dbPapersFacets", runId] as const
}

export function dbOutcomesQueryKey(runId: string) {
  return ["dbOutcomes", runId] as const
}

export function dbPaperSuggestQueryKey(
  runId: string,
  column: "title" | "author",
  query: string,
) {
  return ["dbPaperSuggest", runId, column, query] as const
}

export function useDbPapers(
  runId: string,
  filters: DbPapersFilters,
  page: number,
  pageSize: number,
  options?: { enabled?: boolean; isLive?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbPapersQueryKey(runId, filters, page, pageSize),
    queryFn: () =>
      fetchPapersAll(
        runId,
        "",
        filters.taFilter,
        filters.ftFilter,
        filters.primaryStatusFilter,
        filters.yearFilter,
        filters.sourceFilter,
        filters.countryFilter,
        page * pageSize,
        pageSize,
        filters.titleFilter,
        filters.authorFilter,
      ),
    enabled,
    refetchInterval: options?.isLive ? LIVE_DB_REFRESH_MS : false,
  })
}

export function useDbPapersFacets(runId: string, enabled = true) {
  return useQuery({
    queryKey: dbPapersFacetsQueryKey(runId),
    queryFn: () => fetchPapersFacets(runId),
    enabled: enabled && Boolean(runId),
    staleTime: 60_000,
  })
}

export function useDbOutcomes(runId: string, options?: { enabled?: boolean; isLive?: boolean }) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbOutcomesQueryKey(runId),
    queryFn: () => fetchDbTables(runId),
    enabled,
    refetchInterval: options?.isLive ? LIVE_DB_REFRESH_MS : false,
  })
}

export function useDbPaperSuggest(
  runId: string,
  column: "title" | "author",
  query: string,
) {
  return useQuery({
    queryKey: dbPaperSuggestQueryKey(runId, column, query),
    queryFn: () => fetchPapersSuggest(runId, column, query),
    enabled: Boolean(runId) && Boolean(query),
    staleTime: 30_000,
  })
}

export function papersFetchErrorMessage(error: unknown): string | null {
  const msg = error instanceof Error ? error.message : String(error)
  if (msg.includes("503")) return null
  return msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg
}
