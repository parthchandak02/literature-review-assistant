import { useEffect, useMemo, useState } from "react"
import { Database, FilterX } from "lucide-react"
import { FacetFilters } from "@/components/database/FacetFilters"
import { FilterChipBar } from "@/components/database/FilterChipBar"
import { OutcomesTable } from "@/components/database/OutcomesTable"
import { PaperInspector } from "@/components/database/PaperInspector"
import { PapersTable } from "@/components/database/PapersTable"
import { ColumnsMenu, ExportMenu } from "@/components/database/TableMenus"
import {
  emptyColumns,
  resolveVisibleColumns,
  type ColumnOverrides,
} from "@/components/database/paperColumns"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FetchError, EmptyState, LoadingPane } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { LiveStreamStatus } from "@/components/run-status"
import { TableSkeleton, Pagination } from "@/components/ui/table"
import {
  papersFetchErrorMessage,
  useDbOutcomes,
  useDbPaperSuggest,
  useDbPapers,
  useDbPapersFacets,
} from "@/hooks/useDbPapers"
import { PAGE_SIZE_OPTIONS, useDbFilters, type PageSize } from "@/hooks/useDbFilters"
import { papersExportUrl } from "@/lib/api/db"

interface DatabaseViewProps {
  runId: string
  isDone: boolean
  /** True as soon as the backend emits db_ready (or when a historical run is attached). */
  dbAvailable: boolean
  /** True while the run is in progress and the DB is available (triggers auto-refresh). */
  isLive: boolean
  /** True when the live SSE stream is connected and authoritative. */
  isSSEConnected?: boolean
}

export function DatabaseView(props: DatabaseViewProps) {
  return <DatabaseViewBody key={props.runId} {...props} />
}

function RunStateBadges({ isLive, isDone }: { isLive: boolean; isDone: boolean }) {
  return (
    <>
      {isLive && <LiveStreamStatus mode="compact" />}
      {isDone && (
        <Badge variant="success" size="sm">
          Complete
        </Badge>
      )}
    </>
  )
}

function DatabaseViewBody({ runId, isDone, dbAvailable, isLive, isSSEConnected }: DatabaseViewProps) {
  const table = useDbFilters(runId)
  const { filters, sort, page, pageSize } = table
  const [columnOverrides, setColumnOverrides] = useState<ColumnOverrides>({})
  const [openPaperId, setOpenPaperId] = useState<string | null>(null)

  const liveOptions = { enabled: dbAvailable, isLive, isSSEConnected }
  const papersQuery = useDbPapers(runId, filters, sort, page, pageSize, liveOptions)
  const facetsQuery = useDbPapersFacets(runId, filters, liveOptions)
  const outcomesQuery = useDbOutcomes(runId, liveOptions)
  const titleSuggestionsQuery = useDbPaperSuggest(runId, "title", table.titleSuggestQuery)
  const authorSuggestionsQuery = useDbPaperSuggest(runId, "author", table.authorSuggestQuery)

  const papers = useMemo(() => papersQuery.data?.papers ?? [], [papersQuery.data])
  const total = papersQuery.data?.total ?? 0
  const error = papersQuery.isError ? papersFetchErrorMessage(papersQuery.error) : null
  const hasBootstrapped = papersQuery.isFetched && outcomesQuery.isFetched
  const filterCount = table.activeFilterCount

  const { setPage } = table
  useEffect(() => {
    if (!papersQuery.isFetched || papersQuery.isPlaceholderData) return
    if (page > 0 && page * pageSize >= total) setPage(Math.max(0, Math.ceil(total / pageSize) - 1))
  }, [page, pageSize, total, papersQuery.isFetched, papersQuery.isPlaceholderData, setPage])

  const empty = useMemo(() => emptyColumns(papers), [papers])
  const visibleColumns = useMemo(
    () => resolveVisibleColumns(papers, columnOverrides),
    [papers, columnOverrides],
  )

  const outcomeError = outcomesQuery.isError
    ? outcomesQuery.error instanceof Error
      ? outcomesQuery.error.message
      : String(outcomesQuery.error)
    : null

  if (!dbAvailable) {
    return <LoadingPane message="Database initializing..." className="h-64" />
  }

  if (!hasBootstrapped) {
    return (
      <div className="flex flex-col gap-4">
        <ViewToolbar
          bordered={false}
          className="justify-end"
          actions={<RunStateBadges isLive={isLive} isDone={isDone} />}
        />
        <LoadingPane message="Loading data tables…" className="min-h-72" />
      </div>
    )
  }

  const papersBody = error ? (
    <div className="p-4">
      <FetchError message={error} onRetry={() => void papersQuery.refetch()} />
    </div>
  ) : papersQuery.isLoading ? (
    <TableSkeleton cols={6} rows={5} />
  ) : papers.length === 0 ? (
    filterCount > 0 ? (
      <EmptyState
        icon={FilterX}
        heading={`No papers match ${filterCount} ${filterCount === 1 ? "filter" : "filters"}.`}
        sub="Remove a filter or clear them all to see more papers."
        className="py-12"
        action={
          <Button type="button" size="sm" variant="secondary" onClick={table.clearAllFilters}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={Database}
        heading="No papers in the database yet."
        sub={isLive ? "Papers appear here as the search phase saves them." : undefined}
        className="py-12"
      />
    )
  ) : (
    <PapersTable
      papers={papers}
      visibleColumns={visibleColumns}
      sort={sort}
      onSort={table.toggleSort}
      onOpenPaper={setOpenPaperId}
      selectedPaperId={openPaperId}
    />
  )

  return (
    <div className="flex flex-col gap-4">
      <GlassTableShell>
        <ViewToolbar bordered height="auto" className="flex-wrap gap-3 py-2">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <FacetFilters
              filters={filters}
              facets={facetsQuery.data}
              onToggleFacet={table.toggleFacet}
              onClearFacet={table.clearFacet}
              onYearRange={table.setYearRange}
              onTitleFilterChange={table.setTitleFilter}
              onAuthorFilterChange={table.setAuthorFilter}
              onTitleSuggestQuery={table.setTitleSuggestQuery}
              onAuthorSuggestQuery={table.setAuthorSuggestQuery}
              titleSuggestions={titleSuggestionsQuery.data?.suggestions ?? []}
              authorSuggestions={authorSuggestionsQuery.data?.suggestions ?? []}
              isLoadingTitleSuggestions={titleSuggestionsQuery.isFetching}
              isLoadingAuthorSuggestions={authorSuggestionsQuery.isFetching}
            />
            <FilterChipBar
              filters={table.activeFilterChips}
              onRemove={table.removeFilter}
              onClearAll={table.clearAllFilters}
            />
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <ColumnsMenu
              visible={visibleColumns}
              empty={empty}
              onToggle={(id, visible) => setColumnOverrides((prev) => ({ ...prev, [id]: visible }))}
              onReset={() => setColumnOverrides({})}
            />
            <ExportMenu
              total={total}
              csvUrl={papersExportUrl(runId, filters, sort, "csv")}
              risUrl={papersExportUrl(runId, filters, sort, "ris")}
            />
            <RunStateBadges isLive={isLive} isDone={isDone} />
          </div>
        </ViewToolbar>

        {papersBody}

        {!error && (
          <Pagination
            className="border-t border-border/70 px-3 py-2"
            page={page}
            pageSize={pageSize}
            total={total}
            itemLabel={total === 1 ? "paper" : "papers"}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={(size) => table.setPageSize(size as PageSize)}
            onPrev={() => table.setPage(page - 1)}
            onNext={() => table.setPage(page + 1)}
          />
        )}
      </GlassTableShell>

      <OutcomesTable
        outcomePapers={outcomesQuery.data?.papers ?? []}
        error={outcomeError}
        onRetry={() => void outcomesQuery.refetch()}
      />

      <PaperInspector
        runId={runId}
        paperId={openPaperId}
        onOpenChange={(open) => {
          if (!open) setOpenPaperId(null)
        }}
      />
    </div>
  )
}
