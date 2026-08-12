import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  fetchDbTables,
  fetchPapersAll,
  fetchPapersFacets,
  fetchPapersSuggest,
  type PapersFacets,
} from "@/lib/api"
import { LIVE_DB_REFRESH_MS, resolveLiveQueryRefetchInterval } from "@/lib/pollingBackoff"

export { LIVE_DB_REFRESH_MS }

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
  options?: {
    enabled?: boolean
    isLive?: boolean
    isSSEConnected?: boolean
    includeFacets?: boolean
  },
) {
  const queryClient = useQueryClient()
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbPapersQueryKey(runId, filters, page, pageSize),
    queryFn: async () => {
      const facetsCached = Boolean(
        queryClient.getQueryData<PapersFacets>(dbPapersFacetsQueryKey(runId)),
      )
      const includeFacets = Boolean(options?.includeFacets) && !facetsCached
      const result = await fetchPapersAll(
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
        { includeFacets },
      )
      if (result.facets) {
        queryClient.setQueryData(dbPapersFacetsQueryKey(runId), result.facets)
      }
      return result
    },
    enabled,
    refetchInterval: resolveLiveQueryRefetchInterval(LIVE_DB_REFRESH_MS, {
      isLive: Boolean(options?.isLive),
      isSSEConnected: options?.isSSEConnected,
    }),
    refetchIntervalInBackground: false,
  })
}

export interface DbPapersFacetsOptions {
  /** True when the paired papers query requested include=facets. */
  papersQueryIncludesFacets?: boolean
  /** True once the paired papers query has settled. */
  papersQueryFetched?: boolean
  /** True when the paired papers response included facets. */
  papersHadFacets?: boolean
}

export function useDbPapersFacets(
  runId: string,
  enabled = true,
  options?: DbPapersFacetsOptions,
) {
  const queryClient = useQueryClient()
  const cachedFacets = queryClient.getQueryData<PapersFacets>(dbPapersFacetsQueryKey(runId))
  const waitingForPapersFacets =
    Boolean(options?.papersQueryIncludesFacets) && !options?.papersQueryFetched
  const shouldFallbackFetch =
    enabled &&
    Boolean(runId) &&
    !cachedFacets &&
    !waitingForPapersFacets &&
    (!options?.papersQueryIncludesFacets ||
      (options.papersQueryFetched && !options.papersHadFacets))

  return useQuery({
    queryKey: dbPapersFacetsQueryKey(runId),
    queryFn: () => fetchPapersFacets(runId),
    enabled: shouldFallbackFetch,
    staleTime: 60_000,
    initialData: cachedFacets,
  })
}

export function useDbOutcomes(
  runId: string,
  options?: { enabled?: boolean; isLive?: boolean; isSSEConnected?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: dbOutcomesQueryKey(runId),
    queryFn: () => fetchDbTables(runId),
    enabled,
    refetchInterval: resolveLiveQueryRefetchInterval(LIVE_DB_REFRESH_MS, {
      isLive: Boolean(options?.isLive),
      isSSEConnected: options?.isSSEConnected,
    }),
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
  return msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg
}
