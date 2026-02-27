import { useCallback, useEffect, useRef, useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { FetchError, EmptyState, LoadingPane } from "@/components/ui/feedback"
import { Th, Td, TableSkeleton, Pagination } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { AlertTriangle, Database, ExternalLink, Filter, Loader2, X } from "lucide-react"
// Loader2 is still used in FilterComboboxPopover
import { fetchPapersAll, fetchPapersFacets, fetchPapersSuggest } from "@/lib/api"
import type { PaperAllRow } from "@/lib/api"

const LIVE_REFRESH_MS = 10_000

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

const DECISION_COLOR: Record<string, string> = {
  include: "text-emerald-400",
  exclude: "text-red-400",
  uncertain: "text-amber-400",
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
  const [yearFilter, setYearFilter] = useState("")
  const [sourceFilter, setSourceFilter] = useState("")
  const [countryFilter, setCountryFilter] = useState("")
  const [showHeuristicOnly, setShowHeuristicOnly] = useState(false)
  const [page, setPage] = useState(0)

  const [papers, setPapers] = useState<PaperAllRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Facet data (loaded once on mount / dbAvailable)
  const [years, setYears] = useState<number[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [countries, setCountries] = useState<string[]>([])
  const [taDecisions, setTaDecisions] = useState<string[]>([])
  const [ftDecisions, setFtDecisions] = useState<string[]>([])

  // Title / author suggestions from server
  const [titleSuggestions, setTitleSuggestions] = useState<string[]>([])
  const [authorSuggestions, setAuthorSuggestions] = useState<string[]>([])
  const [isSuggestingTitle, setIsSuggestingTitle] = useState(false)
  const [isSuggestingAuthor, setIsSuggestingAuthor] = useState(false)

  // Keep a ref with current filter values so pagination effect can read them
  // without needing them in its dependency array.
  const filtersRef = useRef({ runId, titleFilter, authorFilter, taFilter, ftFilter, yearFilter, sourceFilter, countryFilter })
  filtersRef.current = { runId, titleFilter, authorFilter, taFilter, ftFilter, yearFilter, sourceFilter, countryFilter }

  function handleFetchError(e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    if (!msg.includes("503")) {
      setError(msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg)
    }
  }

  // Load facets once when DB becomes available
  useEffect(() => {
    if (!dbAvailable) return
    fetchPapersFacets(runId)
      .then((data) => {
        setYears(data.years)
        setSources(data.sources)
        setCountries(data.countries ?? [])
        setTaDecisions(data.ta_decisions ?? [])
        setFtDecisions(data.ft_decisions ?? [])
      })
      .catch(() => {})
  }, [runId, dbAvailable])

  const fetchTitleSuggestions = useCallback(
    (q: string) => {
      if (!q) { setTitleSuggestions([]); return }
      setIsSuggestingTitle(true)
      fetchPapersSuggest(runId, "title", q)
        .then((d) => setTitleSuggestions(d.suggestions))
        .catch(() => setTitleSuggestions([]))
        .finally(() => setIsSuggestingTitle(false))
    },
    [runId],
  )

  const fetchAuthorSuggestions = useCallback(
    (q: string) => {
      if (!q) { setAuthorSuggestions([]); return }
      setIsSuggestingAuthor(true)
      fetchPapersSuggest(runId, "author", q)
        .then((d) => setAuthorSuggestions(d.suggestions))
        .catch(() => setAuthorSuggestions([]))
        .finally(() => setIsSuggestingAuthor(false))
    },
    [runId],
  )

  // Effect 1: any filter or runId change -> reset page to 0 AND fetch with offset=0
  useEffect(() => {
    if (!dbAvailable) return
    setPage(0)
    let cancelled = false
    setLoading(true)
    setError(null)
    const { runId: rid, titleFilter: tl, authorFilter: au, taFilter: ta, ftFilter: ft, yearFilter: yr, sourceFilter: src, countryFilter: ct } =
      filtersRef.current
    fetchPapersAll(rid, "", ta, ft, yr, src, ct, 0, PAGE_SIZE, tl, au)
      .then((data) => {
        if (cancelled) return
        setPapers(data.papers)
        setTotal(data.total)
      })
      .catch((e) => { if (!cancelled) handleFetchError(e) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, titleFilter, authorFilter, taFilter, ftFilter, yearFilter, sourceFilter, countryFilter, dbAvailable])

  // Effect 2: pagination only (page > 0).
  useEffect(() => {
    if (page === 0 || !dbAvailable) return
    let cancelled = false
    setLoading(true)
    setError(null)
    const { runId: rid, titleFilter: tl, authorFilter: au, taFilter: ta, ftFilter: ft, yearFilter: yr, sourceFilter: src, countryFilter: ct } =
      filtersRef.current
    fetchPapersAll(rid, "", ta, ft, yr, src, ct, page * PAGE_SIZE, PAGE_SIZE, tl, au)
      .then((data) => {
        if (cancelled) return
        setPapers(data.papers)
        setTotal(data.total)
      })
      .catch((e) => { if (!cancelled) handleFetchError(e) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, dbAvailable])

  // Auto-refresh every LIVE_REFRESH_MS while run is in progress
  useEffect(() => {
    if (!isLive || !dbAvailable) return
    const id = setInterval(() => {
      const { runId: rid, titleFilter: tl, authorFilter: au, taFilter: ta, ftFilter: ft, yearFilter: yr, sourceFilter: src, countryFilter: ct } =
        filtersRef.current
      fetchPapersAll(rid, "", ta, ft, yr, src, ct, 0, PAGE_SIZE, tl, au)
        .then((data) => { setPapers(data.papers); setTotal(data.total) })
        .catch(() => {})
    }, LIVE_REFRESH_MS)
    return () => clearInterval(id)
  }, [isLive, dbAvailable])

  const loadPapers = () => {
    const { runId: rid, titleFilter: tl, authorFilter: au, taFilter: ta, ftFilter: ft, yearFilter: yr, sourceFilter: src, countryFilter: ct } =
      filtersRef.current
    setLoading(true)
    setError(null)
    fetchPapersAll(rid, "", ta, ft, yr, src, ct, page * PAGE_SIZE, PAGE_SIZE, tl, au)
      .then((data) => { setPapers(data.papers); setTotal(data.total) })
      .catch(handleFetchError)
      .finally(() => setLoading(false))
  }

  const clearAllFilters = () => {
    setTitleFilter("")
    setAuthorFilter("")
    setTaFilter("")
    setFtFilter("")
    setYearFilter("")
    setSourceFilter("")
    setCountryFilter("")
    setShowHeuristicOnly(false)
    setTitleSuggestions([])
    setAuthorSuggestions([])
  }

  if (!dbAvailable) {
    return <LoadingPane message="Database initializing..." className="h-64" />
  }

  const activeFilters = [titleFilter, authorFilter, taFilter, ftFilter, yearFilter, sourceFilter, countryFilter].filter(Boolean).length + (showHeuristicOnly ? 1 : 0)

  // Apply client-side heuristic filter after fetch
  const displayedPapers = showHeuristicOnly
    ? papers.filter((p) => p.assessment_source === "heuristic")
    : papers

  // Hide the Confidence column when no paper on the current page has a value.
  const hasConfidenceData = displayedPapers.some((p) => p.extraction_confidence != null)

  return (
    <div className="flex flex-col gap-4">
      {/* Metadata row */}
      <div className="flex items-center gap-3 flex-wrap">
        {activeFilters > 0 && (
          <button
            onClick={clearAllFilters}
            className="text-xs text-violet-400 hover:text-violet-300 transition-colors whitespace-nowrap"
          >
            Clear {activeFilters} filter{activeFilters > 1 ? "s" : ""}
          </button>
        )}
        <button
          onClick={() => setShowHeuristicOnly((v) => !v)}
          className={cn(
            "flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-colors",
            showHeuristicOnly
              ? "border-amber-600 bg-amber-900/30 text-amber-400"
              : "border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-600",
          )}
        >
          <AlertTriangle className="h-3 w-3" />
          Heuristic screen only
        </button>
        <div className="flex items-center gap-3 ml-auto">
          {!error && (
            <span className="text-xs text-zinc-500 tabular-nums">
              {total.toLocaleString()} papers
            </span>
          )}
          {isLive && (
            <div className="flex items-center gap-1.5 text-xs text-violet-400">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
              </span>
              Live
            </div>
          )}
          {isDone && (
            <span className="text-xs text-emerald-400 font-medium">Complete</span>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="card-surface overflow-hidden">
        {error ? (
          <div className="p-4">
            <FetchError message={error} onRetry={loadPapers} />
          </div>
        ) : loading ? (
          <TableSkeleton cols={9} rows={8} />
        ) : displayedPapers.length === 0 ? (
          <EmptyState icon={Database} heading="No papers found." className="py-12" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <Th
                    filter={
                      <FilterComboboxPopover
                        value={titleFilter}
                        onChange={setTitleFilter}
                        placeholder="Search titles..."
                        serverSuggestions={titleSuggestions}
                        onSuggestionQuery={fetchTitleSuggestions}
                        isLoadingSuggestions={isSuggestingTitle}
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
                        serverSuggestions={authorSuggestions}
                        onSuggestionQuery={fetchAuthorSuggestions}
                        isLoadingSuggestions={isSuggestingAuthor}
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
                    TA Decision
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
                    FT Decision
                  </Th>
                  {hasConfidenceData && <Th>Confidence</Th>}
                  <Th>RoB Source</Th>
                </tr>
              </thead>
              <tbody>
                {displayedPapers.map((p, i) => (
                  <tr
                    key={p.paper_id}
                    className={cn(
                      "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                      i === displayedPapers.length - 1 && "border-0",
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
                            <span className="line-clamp-2 text-zinc-200 group-hover:text-white group-hover:underline underline-offset-2">
                              {p.title}
                            </span>
                            <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 text-zinc-600 group-hover:text-zinc-400 transition-colors" />
                          </a>
                        ) : (
                          <span className="line-clamp-2 text-zinc-200">{p.title}</span>
                        )
                      })()}
                    </Td>
                    <Td className="text-zinc-500 max-w-[160px]">
                      <span className="line-clamp-1">{p.authors}</span>
                    </Td>
                    <Td className="tabular-nums text-zinc-400">{p.year ?? "--"}</Td>
                    <Td className="text-zinc-500">{p.source_database}</Td>
                    <Td className="text-zinc-600">{p.country ?? "--"}</Td>
                    <DecisionCell value={p.ta_decision} />
                    <DecisionCell value={p.ft_decision} />
                    {hasConfidenceData && <ExtractionConfidenceCell value={p.extraction_confidence} />}
                    <AssessmentSourceCell value={p.assessment_source} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Pagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPrev={() => setPage((p) => Math.max(0, p - 1))}
        onNext={() => setPage((p) => p + 1)}
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
            isActive ? "text-violet-400 hover:text-violet-300" : "text-zinc-600 hover:text-zinc-400",
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
            "z-50 w-56 bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl shadow-black/60",
            "overflow-hidden",
          )}
        >
          <Command shouldFilter={false}>
            <div className="relative flex items-center border-b border-zinc-800 px-2">
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
                className="border-0 focus:ring-0 h-8 text-xs bg-transparent text-zinc-200 placeholder:text-zinc-600 py-0"
              />
              {local && (
                <button
                  onMouseDown={(e) => {
                    e.preventDefault()
                    clearValue()
                  }}
                  className="shrink-0 text-zinc-600 hover:text-zinc-300 transition-colors ml-1"
                  aria-label="Clear filter"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <CommandList>
              {isLoadingSuggestions && (
                <div className="py-2 px-3 text-xs text-zinc-600 flex items-center gap-2">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Loading...
                </div>
              )}
              {!isLoadingSuggestions && suggestions.length === 0 && local && (
                <CommandEmpty className="py-3 text-xs text-zinc-600">No matches.</CommandEmpty>
              )}
              {suggestions.length > 0 && (
                <CommandGroup>
                  {suggestions.map((s) => (
                    <CommandItem
                      key={s}
                      value={s}
                      onSelect={() => applyValue(s)}
                      className={cn(
                        "text-xs text-zinc-300 cursor-pointer rounded-md px-2 py-1.5",
                        "data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100",
                      )}
                    >
                      <span className="truncate">{s}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
          <Popover.Arrow className="fill-zinc-800" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

// ---------------------------------------------------------------------------
// Helper cells
// ---------------------------------------------------------------------------

function DecisionCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-zinc-700">--</Td>
  }
  return (
    <Td>
      <span className={cn("font-semibold capitalize", DECISION_COLOR[value] ?? "text-zinc-400")}>
        {value}
      </span>
    </Td>
  )
}

function ExtractionConfidenceCell({ value }: { value: number | null }) {
  if (value == null) {
    return <Td className="text-zinc-700">--</Td>
  }
  const pct = Math.round(value * 100)
  const color =
    pct >= 80
      ? "bg-emerald-900/40 text-emerald-400 border-emerald-800"
      : pct >= 60
        ? "bg-amber-900/40 text-amber-400 border-amber-800"
        : "bg-red-900/40 text-red-400 border-red-800"
  return (
    <Td>
      <span
        className={cn(
          "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border",
          color,
        )}
      >
        {pct}%
      </span>
    </Td>
  )
}

function AssessmentSourceCell({ value }: { value: string | null }) {
  if (!value) {
    return <Td className="text-zinc-700">--</Td>
  }
  if (value === "heuristic") {
    return (
      <Td>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-900/40 text-amber-400 border border-amber-800">
          <AlertTriangle className="h-2.5 w-2.5" />
          heuristic
        </span>
      </Td>
    )
  }
  return (
    <Td>
      <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
        {value}
      </span>
    </Td>
  )
}
