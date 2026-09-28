import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { fetchDbTables, fetchPapersSuggest } from "@/lib/api"
import {
  fetchPaperDetail,
  fetchPapersFacets,
  fetchPapersPage,
  type PapersQuery,
  type PapersSort,
} from "@/lib/api/db"
import { LIVE_DB_REFRESH_MS, resolveLiveQueryRefetchInterval } from "@/lib/pollingBackoff"

export { LIVE_DB_REFRESH_MS }

interface LiveOptions {
  enabled?: boolean
  isLive?: boolean
  isSSEConnected?: boolean
}

function liveInterval(options?: LiveOptions) {
  return resolveLiveQueryRefetchInterval(LIVE_DB_REFRESH_MS, {
    isLive: Boolean(options?.isLive),
    isSSEConnected: options?.isSSEConnected,
  })
}

export function dbPapersQueryKey(
  runId: string,
  filters: PapersQuery,
  sort: PapersSort,
  page: number,
  pageSize: number,
) {
  return ["dbPapers", runId, filters, sort, page, pageSize] as const
}

export function dbPapersFacetsQueryKey(runId: string, filters?: PapersQuery) {
  return filters ? (["dbPapersFacets", runId, filters] as const) : (["dbPapersFacets", runId] as const)
}

export function dbOutcomesQueryKey(runId: string) {
  return ["dbOutcomes", runId] as const
}

export function dbPaperDetailQueryKey(runId: string, paperId: string | null) {
  return ["dbPaperDetail", runId, paperId] as const
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
  filters: PapersQuery,
  sort: PapersSort,
  page: number,
  pageSize: number,
  options?: LiveOptions,
) {
  return useQuery({
    queryKey: dbPapersQueryKey(runId, filters, sort, page, pageSize),
    queryFn: () => fetchPapersPage(runId, filters, sort, page * pageSize, pageSize),
    enabled: (options?.enabled ?? true) && Boolean(runId),
    placeholderData: keepPreviousData,
    refetchInterval: liveInterval(options),
    refetchIntervalInBackground: false,
  })
}

/** Facet values with counts; each facet's counts respect every other active filter. */
export function useDbPapersFacets(runId: string, filters: PapersQuery, options?: LiveOptions) {
  return useQuery({
    queryKey: dbPapersFacetsQueryKey(runId, filters),
    queryFn: () => fetchPapersFacets(runId, filters),
    enabled: (options?.enabled ?? true) && Boolean(runId),
    placeholderData: keepPreviousData,
    staleTime: 15_000,
    refetchInterval: liveInterval(options),
    refetchIntervalInBackground: false,
  })
}

export function useDbPaperDetail(runId: string, paperId: string | null) {
  return useQuery({
    queryKey: dbPaperDetailQueryKey(runId, paperId),
    queryFn: () => fetchPaperDetail(runId, paperId as string),
    enabled: Boolean(runId) && Boolean(paperId),
    staleTime: 30_000,
  })
}

export function useDbOutcomes(runId: string, options?: LiveOptions) {
  return useQuery({
    queryKey: dbOutcomesQueryKey(runId),
    queryFn: () => fetchDbTables(runId),
    enabled: (options?.enabled ?? true) && Boolean(runId),
    refetchInterval: liveInterval(options),
    refetchIntervalInBackground: false,
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
  return msg.toLowerCase().includes("failed to fetch") ? "Can't reach the server." : msg
}
