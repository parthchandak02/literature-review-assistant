import { useEffect, useMemo, useReducer, useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import { FilterChipBar, type ActiveFilter } from "@/components/database/FilterChipBar"
import { FilterComboboxPopover } from "@/components/database/FilterComboboxPopover"
import { FetchError, EmptyState, LoadingPane } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { LiveStreamStatus } from "@/components/run-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Th, Td, TableSkeleton, Pagination } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { AlertTriangle, Database, ExternalLink, Filter } from "lucide-react"
import type { PaperAllRow } from "@/lib/api"
import { confidenceToVariant, screeningDecisionToVariant } from "@/lib/constants"
import {
  papersFetchErrorMessage,
  useDbOutcomes,
  useDbPaperSuggest,
  useDbPapers,
  useDbPapersFacets,
  type DbPapersFilters,
} from "@/hooks/useDbPapers"

/**
 * Resolve the best clickable link for a paper following Crossref DOI display
 * guidelines (https://www.crossref.org/display-guidelines/):
 * DOIs must be displayed as full HTTPS URLs: https://doi.org/10.xxxx/xxxxx
 * Falls back to the connector-provided source URL when no DOI is available.
 */
function paperLink(p: PaperAllRow): string | null {
  if (p.doi) {
    const raw = p.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
    return `https://doi.org/${raw}`
  }
  return p.url ?? null
}
const PAGE_SIZE = 50

type PaperFilterId =
  | "title"
  | "author"
  | "year"
  | "source"
  | "country"
  | "ta"
  | "ft"
  | "primaryStatus"

type PapersPaginationState = {
  filterSignature: string
  runId: string
  page: number
}

type PapersPaginationAction =
  | { type: "set_page"; page: number }
  | { type: "sync_scope"; filterSignature: string; runId: string }

function papersPaginationReducer(
  state: PapersPaginationState,
  action: PapersPaginationAction,
): PapersPaginationState {
  switch (action.type) {
    case "set_page":
      return { ...state, page: action.page }
    case "sync_scope":
      if (state.filterSignature === action.filterSignature && state.runId === action.runId) {
        return state
      }
      return {
        filterSignature: action.filterSignature,
        runId: action.runId,
        page: 0,
      }
    default:
      return state
  }
}

interface DatabaseViewProps {
  runId: string
  isDone: boolean
  /** True as soon as the backend emits db_ready (or when a historical run is attached). */
  dbAvailable: boolean
  /** True while the run is in progress and the DB is available (triggers auto-refresh). */
  isLive: boolean
}

export function DatabaseView({ runId, isDone, dbAvailable, isLive }: DatabaseViewProps) {
  const [titleFilter, setTitleFilter] = useState("")
  const [authorFilter, setAuthorFilter] = useState("")
  const [taFilter, setTaFilter] = useState("")
  const [ftFilter, setFtFilter] = useState("")
  const [primaryStatusFilter, setPrimaryStatusFilter] = useState("")
  const [yearFilter, setYearFilter] = useState("")
  const [sourceFilter, setSourceFilter] = useState("")
  const [countryFilter, setCountryFilter] = useState("")
  const [titleSuggestQuery, setTitleSuggestQuery] = useState("")
  const [authorSuggestQuery, setAuthorSuggestQuery] = useState("")

  const filters = useMemo<DbPapersFilters>(
    () => ({
      titleFilter,
      authorFilter,
      taFilter,
      ftFilter,
      primaryStatusFilter,
      yearFilter,
      sourceFilter,
      countryFilter,
    }),
    [
      titleFilter,
      authorFilter,
      taFilter,
      ftFilter,
      primaryStatusFilter,
      yearFilter,
      sourceFilter,
      countryFilter,
    ],
  )

  const filterSignature = useMemo(
    () =>
      [
        titleFilter,
        authorFilter,
        taFilter,
        ftFilter,
        primaryStatusFilter,
        yearFilter,
        sourceFilter,
        countryFilter,
      ].join("\0"),
    [
      titleFilter,
      authorFilter,
      taFilter,
      ftFilter,
      primaryStatusFilter,
      yearFilter,
      sourceFilter,
      countryFilter,
    ],
  )

  const [pagination, dispatchPagination] = useReducer(papersPaginationReducer, {
    filterSignature,
    runId,
    page: 0,
  })

  useEffect(() => {
    dispatchPagination({ type: "sync_scope", filterSignature, runId })
  }, [filterSignature, runId])

  const queryPage =
    pagination.filterSignature !== filterSignature || pagination.runId !== runId
      ? 0
      : pagination.page

  const isInitialQuery =
    queryPage === 0 &&
    !titleFilter &&
    !authorFilter &&
    !taFilter &&
    !ftFilter &&
    !primaryStatusFilter &&
    !yearFilter &&
    !sourceFilter &&
    !countryFilter

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

  const clearAllFilters = () => {
    setTitleFilter("")
    setAuthorFilter("")
    setTaFilter("")
    setFtFilter("")
    setPrimaryStatusFilter("")
    setYearFilter("")
    setSourceFilter("")
    setCountryFilter("")
    setTitleSuggestQuery("")
    setAuthorSuggestQuery("")
  }

  const activeFilterChips = useMemo<ActiveFilter[]>(() => {
    const chips: ActiveFilter[] = []
    if (titleFilter) chips.push({ id: "title", label: "Title", value: titleFilter })
    if (authorFilter) chips.push({ id: "author", label: "Authors", value: authorFilter })
    if (yearFilter) chips.push({ id: "year", label: "Year", value: yearFilter })
    if (sourceFilter) chips.push({ id: "source", label: "Source", value: sourceFilter })
    if (countryFilter) chips.push({ id: "country", label: "Country", value: countryFilter })
    if (taFilter) chips.push({ id: "ta", label: "Title/Abstract", value: taFilter })
    if (ftFilter) chips.push({ id: "ft", label: "Full-Text", value: ftFilter })
    if (primaryStatusFilter) {
      chips.push({ id: "primaryStatus", label: "Primary Status", value: primaryStatusFilter })
    }
    return chips
  }, [
    titleFilter,
    authorFilter,
    yearFilter,
    sourceFilter,
    countryFilter,
    taFilter,
    ftFilter,
    primaryStatusFilter,
  ])

  const removeFilter = (id: string) => {
    switch (id as PaperFilterId) {
      case "title":
        setTitleFilter("")
        setTitleSuggestQuery("")
        break
      case "author":
        setAuthorFilter("")
        setAuthorSuggestQuery("")
        break
      case "year":
        setYearFilter("")
        break
      case "source":
        setSourceFilter("")
        break
      case "country":
        setCountryFilter("")
        break
      case "ta":
        setTaFilter("")
        break
      case "ft":
        setFtFilter("")
        break
      case "primaryStatus":
        setPrimaryStatusFilter("")
        break
    }
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

  // Hide the Confidence column when no paper on the current page has a value.
  const hasConfidenceData = papers.some((p) => p.extraction_confidence != null)
  const flattenedOutcomes = outcomePapers.flatMap((paper) =>
    paper.outcomes.map((outcome, idx) => ({
      key: `${paper.paper_id}-${idx}-${String(outcome.name ?? "outcome")}`,
      paperTitle: paper.title,
      source: paper.extraction_source,
      name: typeof outcome.name === "string" ? outcome.name : "Outcome",
      effect: outcome.effect_size,
      ci:
        outcome.ci_lower != null && outcome.ci_upper != null
          ? `${outcome.ci_lower} to ${outcome.ci_upper}`
          : null,
      pValue: outcome.p_value,
      n: outcome.n,
    })),
  )

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
          <div className="data-surface overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
                  <Th>Title</Th>
                  <Th>Authors</Th>
                  <Th>Year</Th>
                  <Th>Source</Th>
                  <Th>Country</Th>
                  <Th>Title/Abstract</Th>
                  <Th>Full-Text</Th>
                  <Th>Primary Status</Th>
                  {hasConfidenceData && <Th>Confidence</Th>}
                  <Th>RoB Source</Th>
                </tr>
              </thead>
              <tbody>
                {papers.map((p, i) => (
                  <tr
                    key={p.paper_id}
                    className={cn(
                      "glass-table-row border-b border-border/40",
                      i === papers.length - 1 && "border-0",
                    )}
                  >
                    <Td className="max-w-xs">
                      {(() => {
                        const href = paperLink(p)
                        return href ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="group flex items-start gap-1"
                          >
                            <span className="line-clamp-2 text-foreground group-hover:text-foreground group-hover:underline underline-offset-2">
                              {p.title}
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 text-muted group-hover:text-foreground transition-colors" />
                          </a>
                        ) : (
                          <span className="line-clamp-2 text-foreground">{p.title}</span>
                        )
                      })()}
                    </Td>
                    <Td className="glass-table-cell-muted max-w-[160px]">
                      <span className="line-clamp-1">{p.authors}</span>
                    </Td>
                    <Td className="tabular-nums glass-table-cell-muted">{p.year ?? "--"}</Td>
                    <Td className="glass-table-cell-muted">{p.source_database}</Td>
                    <Td className="glass-table-cell-muted">{p.country ?? "--"}</Td>
                    <DecisionCell value={p.ta_decision} />
                    <DecisionCell value={p.ft_decision} />
                    <PrimaryStatusCell value={p.primary_study_status} />
                    {hasConfidenceData && <ExtractionConfidenceCell value={p.extraction_confidence} />}
                    <AssessmentSourceCell value={p.assessment_source} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassTableShell>

      <GlassTableShell>
        <ViewToolbar
          bordered
          className="!h-auto py-3"
          title={
            <div>
              <div className="text-sm font-semibold text-foreground">Extracted Outcomes</div>
              <div className="text-xs text-muted">
                Deterministic table extraction results from included studies.
              </div>
            </div>
          }
          actions={
            <span className="text-xs text-muted tabular-nums">
              {flattenedOutcomes.length.toLocaleString()} outcome rows
            </span>
          }
        />
        {outcomeError ? (
          <div className="p-4">
            <FetchError message={outcomeError} onRetry={loadOutcomes} />
          </div>
        ) : flattenedOutcomes.length === 0 ? (
          <EmptyState icon={Database} heading="No extracted outcomes yet." className="py-10" />
        ) : (
          <div className="data-surface overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
                  <Th>Paper</Th>
                  <Th>Outcome</Th>
                  <Th>Effect Size</Th>
                  <Th>CI</Th>
                  <Th>P Value</Th>
                  <Th>N</Th>
                  <Th>Source</Th>
                </tr>
              </thead>
              <tbody>
                {flattenedOutcomes.slice(0, 200).map((row) => (
                  <tr key={row.key} className="border-b border-border/80">
                    <Td className="max-w-[28rem] truncate">
                      <span title={row.paperTitle}>{row.paperTitle}</span>
                    </Td>
                    <Td>{row.name}</Td>
                    <Td>{row.effect ?? "-"}</Td>
                    <Td>{row.ci ?? "-"}</Td>
                    <Td>{row.pValue ?? "-"}</Td>
                    <Td>{row.n ?? "-"}</Td>
                    <Td>{row.source}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
            {flattenedOutcomes.length > 200 && (
              <div className="px-4 py-3 text-xs text-muted border-t border-border/70">
                Showing the first 200 outcome rows.
              </div>
            )}
          </div>
        )}
      </GlassTableShell>

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

// ---------------------------------------------------------------------------
// DatabaseFiltersPopover
// ---------------------------------------------------------------------------

interface DatabaseFiltersPopoverProps {
  activeCount: number
  titleFilter: string
  authorFilter: string
  yearFilter: string
  sourceFilter: string
  countryFilter: string
  taFilter: string
  ftFilter: string
  primaryStatusFilter: string
  onTitleFilterChange: (v: string) => void
  onAuthorFilterChange: (v: string) => void
  onYearFilterChange: (v: string) => void
  onSourceFilterChange: (v: string) => void
  onCountryFilterChange: (v: string) => void
  onTaFilterChange: (v: string) => void
  onFtFilterChange: (v: string) => void
  onPrimaryStatusFilterChange: (v: string) => void
  onTitleSuggestQuery: (q: string) => void
  onAuthorSuggestQuery: (q: string) => void
  titleSuggestions: string[]
  authorSuggestions: string[]
  isLoadingTitleSuggestions: boolean
  isLoadingAuthorSuggestions: boolean
  years: number[]
  sources: string[]
  countries: string[]
  taDecisions: string[]
  ftDecisions: string[]
  primaryStatuses: string[]
}

function DatabaseFiltersPopover({
  activeCount,
  titleFilter,
  authorFilter,
  yearFilter,
  sourceFilter,
  countryFilter,
  taFilter,
  ftFilter,
  primaryStatusFilter,
  onTitleFilterChange,
  onAuthorFilterChange,
  onYearFilterChange,
  onSourceFilterChange,
  onCountryFilterChange,
  onTaFilterChange,
  onFtFilterChange,
  onPrimaryStatusFilterChange,
  onTitleSuggestQuery,
  onAuthorSuggestQuery,
  titleSuggestions,
  authorSuggestions,
  isLoadingTitleSuggestions,
  isLoadingAuthorSuggestions,
  years,
  sources,
  countries,
  taDecisions,
  ftDecisions,
  primaryStatuses,
}: DatabaseFiltersPopoverProps) {
  const [open, setOpen] = useState(false)

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="h-8 gap-1.5 shrink-0 text-xs"
        >
          <Filter className="h-3.5 w-3.5" />
          Filters
          {activeCount > 0 && (
            <Badge variant="primary" size="sm" className="tabular-nums px-1.5 min-w-5">
              {activeCount}
            </Badge>
          )}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className={cn(
            "z-50 w-[min(100vw-2rem,20rem)] glass-panel-strong border border-border/80 rounded-xl",
            "shadow-2xl shadow-black/60 overflow-hidden",
          )}
        >
          <div className="px-3 py-2 border-b border-border/70 glass-toolbar">
            <div className="text-xs font-medium text-foreground">Filter papers</div>
            <div className="text-[10px] text-muted">All filters apply together.</div>
          </div>
          <div className="p-3 grid gap-2.5 max-h-[min(70vh,28rem)] overflow-y-auto">
            <FilterComboboxPopover
              label="Title"
              value={titleFilter}
              onChange={onTitleFilterChange}
              placeholder="Search titles..."
              serverSuggestions={titleSuggestions}
              onSuggestionQuery={onTitleSuggestQuery}
              isLoadingSuggestions={isLoadingTitleSuggestions}
            />
            <FilterComboboxPopover
              label="Authors"
              value={authorFilter}
              onChange={onAuthorFilterChange}
              placeholder="Search authors..."
              serverSuggestions={authorSuggestions}
              onSuggestionQuery={onAuthorSuggestQuery}
              isLoadingSuggestions={isLoadingAuthorSuggestions}
            />
            <FilterComboboxPopover
              label="Year"
              value={yearFilter}
              onChange={onYearFilterChange}
              placeholder="Filter year..."
              staticSuggestions={years.map(String)}
            />
            <FilterComboboxPopover
              label="Source"
              value={sourceFilter}
              onChange={onSourceFilterChange}
              placeholder="Filter source..."
              staticSuggestions={sources}
            />
            <FilterComboboxPopover
              label="Country"
              value={countryFilter}
              onChange={onCountryFilterChange}
              placeholder="Filter country..."
              staticSuggestions={countries}
            />
            <FilterComboboxPopover
              label="Title/Abstract"
              value={taFilter}
              onChange={onTaFilterChange}
              placeholder="include / exclude..."
              staticSuggestions={taDecisions}
            />
            <FilterComboboxPopover
              label="Full-Text"
              value={ftFilter}
              onChange={onFtFilterChange}
              placeholder="include / exclude..."
              staticSuggestions={ftDecisions}
            />
            <FilterComboboxPopover
              label="Primary Status"
              value={primaryStatusFilter}
              onChange={onPrimaryStatusFilterChange}
              placeholder="primary / secondary..."
              staticSuggestions={primaryStatuses}
            />
          </div>
          <Popover.Arrow className="fill-surface-2" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

// ---------------------------------------------------------------------------
// Helper cells
// ---------------------------------------------------------------------------

function PrimaryStatusCell({ value }: { value: string | null }) {
  const normalized = (value ?? "unknown").toLowerCase()
  const color =
    normalized === "primary"
      ? "bg-intent-success-subtle text-intent-success border-intent-success-border"
      : normalized === "secondary_review"
        ? "bg-intent-danger-subtle text-intent-danger border-intent-danger-border"
        : normalized === "protocol_only"
          ? "bg-intent-warning-subtle text-intent-warning border-intent-warning-border"
          : normalized === "non_empirical"
            ? "bg-surface-2 text-foreground border-border"
            : "bg-card/60 text-muted border-border"
  return (
    <Td>
      <span className={cn("inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border", color)}>
        {normalized}
      </span>
    </Td>
  )
}

function DecisionCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-muted">--</Td>
  }
  return (
    <Td>
      <Badge variant={screeningDecisionToVariant(value)} size="sm" className="capitalize">
        {value}
      </Badge>
    </Td>
  )
}

function ExtractionConfidenceCell({ value }: { value: number | null }) {
  if (value == null) {
    return <Td className="text-muted">--</Td>
  }
  const pct = Math.round(value * 100)
  return (
    <Td>
      <Badge variant={confidenceToVariant(value)} size="sm" className="font-mono">
        {pct}%
      </Badge>
    </Td>
  )
}

function AssessmentSourceCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-muted">--</Td>
  }
  if (value === "heuristic") {
    return (
      <Td>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-intent-warning-subtle text-intent-warning border border-intent-warning-border">
          <AlertTriangle className="h-2.5 w-2.5" />
          heuristic
        </span>
      </Td>
    )
  }
  return (
    <Td>
      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-surface-2 text-muted border border-border">
        {value}
      </span>
    </Td>
  )
}
