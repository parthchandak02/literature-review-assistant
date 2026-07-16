import { useEffect, useMemo, useReducer, useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { FetchError, EmptyState, LoadingPane, Spinner } from "@/components/ui/feedback"
import { GlassTableShell } from "@/components/ui/glass-table-shell"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { LiveStreamStatus } from "@/components/run-status"
import { Badge } from "@/components/ui/badge"
import { Th, Td, TableSkeleton, Pagination } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { AlertTriangle, Database, ExternalLink, Filter, X } from "lucide-react"
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
const SUGGEST_DEBOUNCE_MS = 200
const FILTER_DEBOUNCE_MS = 350

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

  const papersQuery = useDbPapers(runId, filters, queryPage, PAGE_SIZE, {
    enabled: dbAvailable,
    isLive,
  })
  const facetsQuery = useDbPapersFacets(runId, dbAvailable)
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

  const activeFilters = [
    titleFilter,
    authorFilter,
    taFilter,
    ftFilter,
    primaryStatusFilter,
    yearFilter,
    sourceFilter,
    countryFilter,
  ].filter(Boolean).length

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
          {activeFilters > 0 && (
            <button
              onClick={clearAllFilters}
              className="text-xs text-intent-primary hover:text-intent-primary transition-colors whitespace-nowrap"
            >
              Clear {activeFilters} filter{activeFilters > 1 ? "s" : ""}
            </button>
          )}
          <div className="flex items-center gap-3 ml-auto">
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
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={titleFilter}
                        onChange={setTitleFilter}
                        placeholder="Search titles..."
                        serverSuggestions={titleSuggestionsQuery.data?.suggestions ?? []}
                        onSuggestionQuery={setTitleSuggestQuery}
                        isLoadingSuggestions={titleSuggestionsQuery.isFetching}
                      />
                    }
                  >
                    Title
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={authorFilter}
                        onChange={setAuthorFilter}
                        placeholder="Search authors..."
                        serverSuggestions={authorSuggestionsQuery.data?.suggestions ?? []}
                        onSuggestionQuery={setAuthorSuggestQuery}
                        isLoadingSuggestions={authorSuggestionsQuery.isFetching}
                      />
                    }
                  >
                    Authors
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={yearFilter}
                        onChange={setYearFilter}
                        placeholder="Filter year..."
                        staticSuggestions={years.map(String)}
                      />
                    }
                  >
                    Year
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={sourceFilter}
                        onChange={setSourceFilter}
                        placeholder="Filter source..."
                        staticSuggestions={sources}
                      />
                    }
                  >
                    Source
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={countryFilter}
                        onChange={setCountryFilter}
                        placeholder="Filter country..."
                        staticSuggestions={countries}
                      />
                    }
                  >
                    Country
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={taFilter}
                        onChange={setTaFilter}
                        placeholder="include / exclude..."
                        staticSuggestions={taDecisions}
                      />
                    }
                  >
                    Title/Abstract
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={ftFilter}
                        onChange={setFtFilter}
                        placeholder="include / exclude..."
                        staticSuggestions={ftDecisions}
                      />
                    }
                  >
                    Full-Text
                  </Th>
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={primaryStatusFilter}
                        onChange={setPrimaryStatusFilter}
                        placeholder="primary / secondary..."
                        staticSuggestions={primaryStatuses}
                      />
                    }
                  >
                    Primary Status
                  </Th>
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
// FilterComboboxPopover
// ---------------------------------------------------------------------------

interface FilterComboboxPopoverProps {
  value: string
  onChange: (v: string) => void
  placeholder: string
  /** Categorical columns: pass all distinct values, filtered client-side by query. */
  staticSuggestions?: string[]
  /** Text columns: parent provides server-fetched suggestions. */
  serverSuggestions?: string[]
  /** Called with the debounced query so parent can fetch server suggestions. */
  onSuggestionQuery?: (q: string) => void
  isLoadingSuggestions?: boolean
}

function FilterComboboxPopover({
  value,
  onChange,
  placeholder,
  staticSuggestions,
  serverSuggestions,
  onSuggestionQuery,
  isLoadingSuggestions = false,
}: FilterComboboxPopoverProps) {
  const [open, setOpen] = useState(false)
  const [local, setLocal] = useState(value)
  const isActive = value !== ""

  // Sync external reset (e.g. "Clear N filters" button) back to local state.
  useEffect(() => {
    setLocal(value)
  }, [value])

  // 200ms debounce for fetching server suggestions.
  useEffect(() => {
    if (!onSuggestionQuery) return
    const t = setTimeout(() => onSuggestionQuery(local), SUGGEST_DEBOUNCE_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local])

  // 350ms debounce for applying the table filter.
  useEffect(() => {
    const t = setTimeout(() => onChange(local), FILTER_DEBOUNCE_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local])

  // For static suggestions, filter client-side.
  const suggestions = staticSuggestions
    ? staticSuggestions.filter((s) => s.toLowerCase().includes(local.toLowerCase()))
    : (serverSuggestions ?? [])

  const applyValue = (v: string) => {
    setLocal(v)
    onChange(v)
    setOpen(false)
  }

  const clearValue = () => {
    setLocal("")
    onChange("")
    if (onSuggestionQuery) onSuggestionQuery("")
    setOpen(false)
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          className={cn(
            "flex items-center justify-center h-4 w-4 rounded transition-colors",
            isActive ? "text-intent-primary hover:text-intent-primary" : "text-muted hover:text-foreground",
          )}
          aria-label="Filter column"
        >
          <Filter className="h-3 w-3" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          onInteractOutside={() => setOpen(false)}
          className={cn(
            "z-50 w-56 glass-panel-strong border border-border/80 rounded-xl shadow-2xl shadow-black/60",
            "overflow-hidden",
          )}
        >
          <Command shouldFilter={false}>
            <div className="relative flex items-center border-b border-border/80 px-2 glass-toolbar">
              <CommandInput
                value={local}
                onValueChange={(v) => setLocal(v)}
                placeholder={placeholder}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    // Immediately flush the filter without waiting for debounce.
                    onChange(local)
                    setOpen(false)
                  }
                  if (e.key === "Escape") {
                    setOpen(false)
                  }
                }}
                className="border-0 focus:ring-0 h-8 text-xs bg-transparent text-foreground placeholder:text-muted py-0"
              />
              {local && (
                <button
                  onMouseDown={(e) => {
                    e.preventDefault()
                    clearValue()
                  }}
                  className="shrink-0 text-muted hover:text-foreground transition-colors ml-1"
                  aria-label="Clear filter"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <CommandList>
              {isLoadingSuggestions && (
                <div className="py-2 px-3 text-xs text-muted flex items-center gap-2">
                  <Spinner size="sm" />
                  Loading...
                </div>
              )}
              {!isLoadingSuggestions && suggestions.length === 0 && local && (
                <CommandEmpty className="py-3 text-xs text-muted">No matches.</CommandEmpty>
              )}
              {suggestions.length > 0 && (
                <CommandGroup>
                  {suggestions.map((s) => (
                    <CommandItem
                      key={s}
                      value={s}
                      onSelect={() => applyValue(s)}
                      className={cn(
                        "text-xs text-foreground cursor-pointer rounded-md px-2 py-1.5",
                        "data-[selected=true]:bg-intent-primary-subtle data-[selected=true]:text-intent-primary",
                      )}
                    >
                      <span className="truncate">{s}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
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
