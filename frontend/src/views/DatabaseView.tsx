import { useCallback, useEffect, useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { cn } from "@/lib/utils"
import { ChevronLeft, ChevronRight, Database, Filter, Loader2, Search } from "lucide-react"
import { fetchPapersAll } from "@/lib/api"
import type { PaperAllRow } from "@/lib/api"

const LIVE_REFRESH_MS = 10_000

const DECISION_COLOR: Record<string, string> = {
  include: "text-emerald-400",
  exclude: "text-red-400",
  uncertain: "text-amber-400",
}

const DECISION_OPTIONS = ["", "include", "exclude", "uncertain"] as const

interface DatabaseViewProps {
  runId: string
  isDone: boolean
  /** True as soon as the backend emits db_ready (or when a historical run is attached). */
  dbAvailable: boolean
  /** True while the run is in progress and the DB is available (triggers auto-refresh). */
  isLive: boolean
}

export function DatabaseView({ runId, isDone, dbAvailable, isLive }: DatabaseViewProps) {
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [taFilter, setTaFilter] = useState("")
  const [ftFilter, setFtFilter] = useState("")
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  const [papers, setPapers] = useState<PaperAllRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  const loadPapers = useCallback(async () => {
    if (!dbAvailable) return
    setLoading(true)
    setError(null)
    try {
      const data = await fetchPapersAll(
        runId,
        debouncedSearch,
        taFilter,
        ftFilter,
        page * PAGE_SIZE,
        PAGE_SIZE,
      )
      setPapers(data.papers)
      setTotal(data.total)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      // Suppress 503 "initializing" errors silently -- the auto-refresh will retry.
      if (!msg.includes("503")) {
        setError(msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg)
      }
    } finally {
      setLoading(false)
    }
  }, [runId, page, debouncedSearch, taFilter, ftFilter, dbAvailable])

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [debouncedSearch, taFilter, ftFilter])

  useEffect(() => {
    loadPapers()
  }, [loadPapers])

  // Auto-refresh every LIVE_REFRESH_MS while run is in progress
  useEffect(() => {
    if (!isLive) return
    const id = setInterval(loadPapers, LIVE_REFRESH_MS)
    return () => clearInterval(id)
  }, [isLive, loadPapers])

  if (!dbAvailable) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <Loader2 className="h-8 w-8 text-zinc-600 animate-spin" />
        <p className="text-zinc-500 text-sm">Database initializing...</p>
        <p className="text-zinc-600 text-xs">Data will appear here once the run begins.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Filter bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 min-w-[180px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
          <Input
            value={search}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
            placeholder="Search title or abstract..."
            className="pl-8 bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 h-8 text-sm"
          />
        </div>
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
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
        {error ? (
          <div className="p-4">
            <FetchError message={error} onRetry={loadPapers} />
          </div>
        ) : loading ? (
          <TableSkeleton cols={7} rows={8} />
        ) : papers.length === 0 ? (
          <EmptyState icon={Database} heading="No papers found." className="py-12" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800">
                  <Th>Title</Th>
                  <Th>Authors</Th>
                  <Th>Year</Th>
                  <Th>Source</Th>
                  <Th>Country</Th>
                  <Th filter={<ColumnFilterPopover value={taFilter} onChange={setTaFilter} />}>
                    TA Decision
                  </Th>
                  <Th filter={<ColumnFilterPopover value={ftFilter} onChange={setFtFilter} />}>
                    FT Decision
                  </Th>
                </tr>
              </thead>
              <tbody>
                {papers.map((p, i) => (
                  <tr
                    key={p.paper_id}
                    className={cn(
                      "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                      i === papers.length - 1 && "border-0",
                    )}
                  >
                    <Td className="max-w-xs">
                      <span className="line-clamp-2 text-zinc-200">{p.title}</span>
                    </Td>
                    <Td className="text-zinc-500 max-w-[160px]">
                      <span className="line-clamp-1">{p.authors}</span>
                    </Td>
                    <Td className="tabular-nums text-zinc-400">{p.year ?? "--"}</Td>
                    <Td className="text-zinc-500">{p.source_database}</Td>
                    <Td className="text-zinc-600">{p.country ?? "--"}</Td>
                    <DecisionCell value={p.ta_decision} />
                    <DecisionCell value={p.ft_decision} />
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
// Sub-components
// ---------------------------------------------------------------------------

function ColumnFilterPopover({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const isActive = value !== ""
  return (
    <Popover.Root>
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
          className="z-50 flex items-center gap-0.5 bg-zinc-900 border border-zinc-800 rounded-lg p-1 shadow-xl shadow-black/40"
        >
          {DECISION_OPTIONS.map((d) => (
            <button
              key={d || "all"}
              onClick={() => onChange(d)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-colors whitespace-nowrap",
                value === d ? "bg-zinc-700 text-white" : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {d ? d.charAt(0).toUpperCase() + d.slice(1) : "All"}
            </button>
          ))}
          <Popover.Arrow className="fill-zinc-800" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

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

// ---------------------------------------------------------------------------
// Shared table primitives
// ---------------------------------------------------------------------------

function Th({
  children,
  align,
  filter,
}: {
  children: React.ReactNode
  align?: "right"
  filter?: React.ReactNode
}) {
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {filter ? (
        <div className="flex items-center gap-1.5">
          <span>{children}</span>
          {filter}
        </div>
      ) : (
        children
      )}
    </th>
  )
}

function Td({
  children,
  className,
  align,
}: {
  children: React.ReactNode
  className?: string
  align?: "right"
}) {
  return (
    <td
      className={cn(
        "px-4 py-2.5",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </td>
  )
}

function Pagination({
  page,
  pageSize,
  total,
  onPrev,
  onNext,
}: {
  page: number
  pageSize: number
  total: number
  onPrev: () => void
  onNext: () => void
}) {
  const start = page * pageSize + 1
  const end = Math.min((page + 1) * pageSize, total)
  const hasPrev = page > 0
  const hasNext = end < total

  if (total <= pageSize) return null

  return (
    <div className="flex items-center justify-between text-xs text-zinc-500">
      <span>
        {start}-{end} of {total.toLocaleString()}
      </span>
      <div className="flex gap-1">
        <Button
          size="sm"
          variant="outline"
          onClick={onPrev}
          disabled={!hasPrev}
          className="h-7 w-7 p-0 border-zinc-800"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onNext}
          disabled={!hasNext}
          className="h-7 w-7 p-0 border-zinc-800"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}

function TableSkeleton({ cols, rows }: { cols: number; rows: number }) {
  return (
    <div className="p-4 space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3">
          {Array.from({ length: cols }).map((_, j) => (
            <div
              key={j}
              className="h-4 bg-zinc-800 rounded animate-pulse"
              style={{ flex: j === 0 ? 3 : 1 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}
