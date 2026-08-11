import { FilterChipBar } from "@/components/database/FilterChipBar"
import { DatabaseFiltersPopover } from "@/components/database/DatabaseFiltersPopover"
import { OutcomesTable } from "@/components/database/OutcomesTable"
import { PapersTable } from "@/components/database/PapersTable"
import { FetchError, EmptyState, LoadingPane } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { LiveStreamStatus } from "@/components/run-status"
import { TableSkeleton, Pagination } from "@/components/ui/table"
import { Database } from "lucide-react"
import {
  papersFetchErrorMessage,
  useDbOutcomes,
  useDbPaperSuggest,
  useDbPapers,
  useDbPapersFacets,
} from "@/hooks/useDbPapers"
import { useDbFilters } from "@/hooks/useDbFilters"

const PAGE_SIZE = 50

interface DatabaseViewProps {
  runId: string
  isDone: boolean
  /** True as soon as the backend emits db_ready (or when a historical run is attached). */
  dbAvailable: boolean
  /** True while the run is in progress and the DB is available (triggers auto-refresh). */
  isLive: boolean
}

export function DatabaseView(props: DatabaseViewProps) {
  return <DatabaseViewBody key={props.runId} {...props} />
}

function DatabaseViewBody({ runId, isDone, dbAvailable, isLive }: DatabaseViewProps) {
  const {
    filters,
    queryPage,
    dispatchPagination,
    isInitialQuery,
    titleFilter,
    setTitleFilter,
    authorFilter,
    setAuthorFilter,
    taFilter,
    setTaFilter,
    ftFilter,
    setFtFilter,
    primaryStatusFilter,
    setPrimaryStatusFilter,
    yearFilter,
    setYearFilter,
    sourceFilter,
    setSourceFilter,
    countryFilter,
    setCountryFilter,
    setTitleSuggestQuery,
    setAuthorSuggestQuery,
    titleSuggestQuery,
    authorSuggestQuery,
    activeFilterChips,
    clearAllFilters,
    removeFilter,
  } = useDbFilters(runId)

  const papersQuery = useDbPapers(runId, filters, queryPage, PAGE_SIZE, {
    enabled: dbAvailable,
    isLive,
    includeFacets: isInitialQuery,
  })
  const facetsQuery = useDbPapersFacets(runId, dbAvailable, {
    papersQueryIncludesFacets: isInitialQuery,
    papersQueryFetched: papersQuery.isFetched,
    papersHadFacets: Boolean(papersQuery.data?.facets),
  })
  const outcomesQuery = useDbOutcomes(runId, { enabled: dbAvailable, isLive })
  const titleSuggestionsQuery = useDbPaperSuggest(runId, "title", titleSuggestQuery)
  const authorSuggestionsQuery = useDbPaperSuggest(runId, "author", authorSuggestQuery)

  const papers = papersQuery.data?.papers ?? []
  const total = papersQuery.data?.total ?? 0
  const loading = papersQuery.isLoading
  const error = papersQuery.isError ? papersFetchErrorMessage(papersQuery.error) : null
  const hasBootstrapped = papersQuery.isFetched && outcomesQuery.isFetched

  const years = facetsQuery.data?.years ?? []
  const sources = facetsQuery.data?.sources ?? []
  const countries = facetsQuery.data?.countries ?? []
  const taDecisions = facetsQuery.data?.ta_decisions ?? []
  const ftDecisions = facetsQuery.data?.ft_decisions ?? []
  const primaryStatuses = facetsQuery.data?.primary_statuses ?? []

  const outcomePapers = outcomesQuery.data?.papers ?? []
  const outcomeError = outcomesQuery.isError
    ? outcomesQuery.error instanceof Error
      ? outcomesQuery.error.message
      : String(outcomesQuery.error)
    : null

  const loadPapers = () => {
    void papersQuery.refetch()
  }

  const loadOutcomes = () => {
    void outcomesQuery.refetch()
  }

  if (!dbAvailable) {
    return <LoadingPane message="Database initializing..." className="h-64" />
  }

  // First visit only: wait for papers + outcomes so we never show one table above the other's skeleton.
  if (!hasBootstrapped) {
    return (
      <div className="flex flex-col gap-4">
        <ViewToolbar
          bordered={false}
          className="justify-end"
          actions={
            <>
              {isLive && <LiveStreamStatus mode="compact" />}
              {isDone && (
                <span className="text-xs text-intent-success font-medium">Complete</span>
              )}
            </>
          }
        />
        <LoadingPane message="Loading data tables…" className="min-h-72" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <GlassTableShell>
        <ViewToolbar bordered className="flex-wrap !h-auto py-2 gap-3">
          <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
            <DatabaseFiltersPopover
              activeCount={activeFilterChips.length}
              titleFilter={titleFilter}
              authorFilter={authorFilter}
              yearFilter={yearFilter}
              sourceFilter={sourceFilter}
              countryFilter={countryFilter}
              taFilter={taFilter}
              ftFilter={ftFilter}
              primaryStatusFilter={primaryStatusFilter}
              onTitleFilterChange={setTitleFilter}
              onAuthorFilterChange={setAuthorFilter}
              onYearFilterChange={setYearFilter}
              onSourceFilterChange={setSourceFilter}
              onCountryFilterChange={setCountryFilter}
              onTaFilterChange={setTaFilter}
              onFtFilterChange={setFtFilter}
              onPrimaryStatusFilterChange={setPrimaryStatusFilter}
              onTitleSuggestQuery={setTitleSuggestQuery}
              onAuthorSuggestQuery={setAuthorSuggestQuery}
              titleSuggestions={titleSuggestionsQuery.data?.suggestions ?? []}
              authorSuggestions={authorSuggestionsQuery.data?.suggestions ?? []}
              isLoadingTitleSuggestions={titleSuggestionsQuery.isFetching}
              isLoadingAuthorSuggestions={authorSuggestionsQuery.isFetching}
              years={years}
              sources={sources}
              countries={countries}
              taDecisions={taDecisions}
              ftDecisions={ftDecisions}
              primaryStatuses={primaryStatuses}
            />
            <FilterChipBar
              filters={activeFilterChips}
              onRemove={removeFilter}
              onClearAll={clearAllFilters}
            />
          </div>
          <div className="flex items-center gap-3 ml-auto shrink-0">
            {!error && (
              <span className="text-xs text-muted tabular-nums">
                {total.toLocaleString()} papers
              </span>
            )}
            {isLive && <LiveStreamStatus mode="compact" />}
            {isDone && (
              <span className="text-xs text-intent-success font-medium">Complete</span>
            )}
          </div>
        </ViewToolbar>

        {error ? (
          <div className="p-4">
            <FetchError message={error} onRetry={loadPapers} />
          </div>
        ) : loading ? (
          <TableSkeleton cols={10} rows={5} />
        ) : papers.length === 0 ? (
          <EmptyState icon={Database} heading="No papers found." className="py-12" />
        ) : (
          <PapersTable papers={papers} />
        )}
      </GlassTableShell>

      <OutcomesTable
        outcomePapers={outcomePapers}
        error={outcomeError}
        onRetry={loadOutcomes}
      />

      <Pagination
        page={queryPage}
        pageSize={PAGE_SIZE}
        total={total}
        onPrev={() =>
          dispatchPagination({ type: "set_page", page: Math.max(0, queryPage - 1) })
        }
        onNext={() => dispatchPagination({ type: "set_page", page: queryPage + 1 })}
      />
    </div>
  )
}
