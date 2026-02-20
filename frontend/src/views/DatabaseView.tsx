import { useCallback, useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AlertTriangle, ChevronLeft, ChevronRight, Database, Loader2, Search } from "lucide-react"
import { fetchPapers, fetchScreening, fetchDbCosts } from "@/lib/api"
import type { PaperRow, ScreeningRow, DbCostRow } from "@/lib/api"

const LIVE_REFRESH_MS = 10_000

type DbTab = "papers" | "screening" | "costs"

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
  const [activeTab, setActiveTab] = useState<DbTab>("papers")
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [page, setPage] = useState(0)
  const PAGE_SIZE = 50

  // Papers
  const [papers, setPapers] = useState<PaperRow[]>([])
  const [papersTotal, setPapersTotal] = useState(0)
  const [papersLoading, setPapersLoading] = useState(false)
  const [papersError, setPapersError] = useState<string | null>(null)

  // Screening
  const [decisions, setDecisions] = useState<ScreeningRow[]>([])
  const [decisionsTotal, setDecisionsTotal] = useState(0)
  const [decisionFilter, setDecisionFilter] = useState("")
  const [decisionsLoading, setDecisionsLoading] = useState(false)
  const [decisionsError, setDecisionsError] = useState<string | null>(null)

  // Costs
  const [costRows, setCostRows] = useState<DbCostRow[]>([])
  const [costTotal, setCostTotal] = useState(0)
  const [costsLoading, setCostsLoading] = useState(false)
  const [costsError, setCostsError] = useState<string | null>(null)

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])

  const loadPapers = useCallback(async () => {
    if (!dbAvailable) return
    setPapersLoading(true)
    setPapersError(null)
    try {
      const data = await fetchPapers(runId, page * PAGE_SIZE, PAGE_SIZE, debouncedSearch)
      setPapers(data.papers)
      setPapersTotal(data.total)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      // Suppress 503 "initializing" errors silently -- the auto-refresh will retry.
      if (!msg.includes("503")) {
        setPapersError(
          msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg,
        )
      }
    } finally {
      setPapersLoading(false)
    }
  }, [runId, page, debouncedSearch, dbAvailable])

  const loadScreening = useCallback(async () => {
    if (!dbAvailable) return
    setDecisionsLoading(true)
    setDecisionsError(null)
    try {
      const data = await fetchScreening(runId, "", decisionFilter, page * PAGE_SIZE, PAGE_SIZE)
      setDecisions(data.decisions)
      setDecisionsTotal(data.total)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (!msg.includes("503")) {
        setDecisionsError(
          msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg,
        )
      }
    } finally {
      setDecisionsLoading(false)
    }
  }, [runId, page, decisionFilter, dbAvailable])

  const loadCosts = useCallback(async () => {
    if (!dbAvailable) return
    setCostsLoading(true)
    setCostsError(null)
    try {
      const data = await fetchDbCosts(runId)
      setCostRows(data.records)
      setCostTotal(data.total_cost)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      if (!msg.includes("503")) {
        setCostsError(
          msg.toLowerCase().includes("failed to fetch") ? "Cannot reach backend" : msg,
        )
      }
    } finally {
      setCostsLoading(false)
    }
  }, [runId, dbAvailable])

  useEffect(() => {
    if (activeTab === "papers") loadPapers()
  }, [activeTab, loadPapers])

  useEffect(() => {
    if (activeTab === "screening") loadScreening()
  }, [activeTab, loadScreening])

  useEffect(() => {
    if (activeTab === "costs") loadCosts()
  }, [activeTab, loadCosts])

  useEffect(() => {
    setPage(0)
  }, [activeTab, debouncedSearch, decisionFilter])

  // Auto-refresh every LIVE_REFRESH_MS while the run is in progress so data
  // populates in near-real-time without any user action.
  useEffect(() => {
    if (!isLive) return
    const tick = () => {
      if (activeTab === "papers") loadPapers()
      else if (activeTab === "screening") loadScreening()
      else if (activeTab === "costs") loadCosts()
    }
    const id = setInterval(tick, LIVE_REFRESH_MS)
    return () => clearInterval(id)
  }, [isLive, activeTab, loadPapers, loadScreening, loadCosts])

  // Show an initializing placeholder until the backend signals the DB is ready.
  if (!dbAvailable) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <Loader2 className="h-8 w-8 text-zinc-600 animate-spin" />
        <p className="text-zinc-500 text-sm">Database initializing...</p>
        <p className="text-zinc-600 text-xs">Data will appear here once the run begins.</p>
      </div>
    )
  }

  const TABS: { id: DbTab; label: string }[] = [
    { id: "papers", label: "Papers" },
    { id: "screening", label: "Screening" },
    { id: "costs", label: "Cost Records" },
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* Tab bar + live badge */}
      <div className="flex items-center gap-3">
        <div
          role="tablist"
          aria-label="Database explorer tabs"
          className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-xl p-1 w-fit"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={activeTab === t.id}
              aria-controls={`panel-${t.id}`}
              id={`tab-${t.id}`}
              onClick={() => setActiveTab(t.id)}
              className={cn(
                "px-4 py-1.5 rounded-lg text-sm font-medium transition-colors",
                activeTab === t.id
                  ? "bg-zinc-700 text-white"
                  : "text-zinc-500 hover:text-zinc-300",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
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

      {/* Papers tab */}
      {activeTab === "papers" && (
        <div
          role="tabpanel"
          id="panel-papers"
          aria-labelledby="tab-papers"
          className="flex flex-col gap-3"
        >
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
              <Input
                value={search}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
                placeholder="Search title or abstract..."
                className="pl-8 bg-zinc-900 border-zinc-800 text-zinc-200 placeholder:text-zinc-600 h-8 text-sm"
              />
            </div>
            {!papersError && (
              <span className="text-xs text-zinc-500 tabular-nums">
                {papersTotal.toLocaleString()} papers
              </span>
            )}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {papersError ? (
              <FetchError msg={papersError} onRetry={loadPapers} />
            ) : papersLoading ? (
              <TableSkeleton cols={5} rows={8} />
            ) : papers.length === 0 ? (
              <EmptyState icon={Database} msg="No papers found." />
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
                        <Td className="text-zinc-500 max-w-[180px]">
                          <span className="line-clamp-1">{p.authors}</span>
                        </Td>
                        <Td className="tabular-nums text-zinc-400">{p.year ?? "--"}</Td>
                        <Td className="text-zinc-500">{p.source_database}</Td>
                        <Td className="text-zinc-600">{p.country ?? "--"}</Td>
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
            total={papersTotal}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </div>
      )}

      {/* Screening tab */}
      {activeTab === "screening" && (
        <div
          role="tabpanel"
          id="panel-screening"
          aria-labelledby="tab-screening"
          className="flex flex-col gap-3"
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-800 rounded-lg p-0.5">
              {["", "include", "exclude", "uncertain"].map((d) => (
                <button
                  key={d || "all"}
                  onClick={() => setDecisionFilter(d)}
                  className={cn(
                    "px-3 py-1 rounded-md text-xs font-medium transition-colors",
                    decisionFilter === d
                      ? "bg-zinc-700 text-white"
                      : "text-zinc-500 hover:text-zinc-300",
                  )}
                >
                  {d || "All"}
                </button>
              ))}
            </div>
            {!decisionsError && (
              <span className="text-xs text-zinc-500 tabular-nums">
                {decisionsTotal.toLocaleString()} decisions
              </span>
            )}
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {decisionsError ? (
              <FetchError msg={decisionsError} onRetry={loadScreening} />
            ) : decisionsLoading ? (
              <TableSkeleton cols={4} rows={8} />
            ) : decisions.length === 0 ? (
              <EmptyState icon={Database} msg="No screening decisions found." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800">
                      <Th>Paper ID</Th>
                      <Th>Stage</Th>
                      <Th>Decision</Th>
                      <Th>Rationale</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {decisions.map((d, i) => (
                      <tr
                        key={`${d.paper_id}-${d.stage}-${i}`}
                        className={cn(
                          "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                          i === decisions.length - 1 && "border-0",
                        )}
                      >
                        <Td className="font-mono text-zinc-500">{d.paper_id?.slice(0, 12)}...</Td>
                        <Td className="text-zinc-400">{d.stage}</Td>
                        <Td>
                          <span
                            className={cn(
                              "font-semibold",
                              DECISION_COLOR[d.decision ?? ""] ?? "text-zinc-400",
                            )}
                          >
                            {d.decision}
                          </span>
                        </Td>
                        <Td className="text-zinc-600 max-w-xs">
                          <span className="line-clamp-1">{d.rationale ?? "--"}</span>
                        </Td>
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
            total={decisionsTotal}
            onPrev={() => setPage((p) => Math.max(0, p - 1))}
            onNext={() => setPage((p) => p + 1)}
          />
        </div>
      )}

      {/* Costs tab */}
      {activeTab === "costs" && (
        <div
          role="tabpanel"
          id="panel-costs"
          aria-labelledby="tab-costs"
          className="flex flex-col gap-3"
        >
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">
              Total from DB:{" "}
              <span className="font-mono text-emerald-400 font-semibold">${costTotal.toFixed(4)}</span>
            </span>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {costsError ? (
              <FetchError msg={costsError} onRetry={loadCosts} />
            ) : costsLoading ? (
              <TableSkeleton cols={6} rows={6} />
            ) : costRows.length === 0 ? (
              <EmptyState icon={Database} msg="No cost records found." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800">
                      <Th>Model</Th>
                      <Th>Phase</Th>
                      <Th align="right">Calls</Th>
                      <Th align="right">Tokens In</Th>
                      <Th align="right">Tokens Out</Th>
                      <Th align="right">Avg Latency</Th>
                      <Th align="right">Cost</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {costRows.map((r, i) => (
                      <tr
                        key={`${r.model}-${r.phase}-${i}`}
                        className={cn(
                          "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                          i === costRows.length - 1 && "border-0",
                        )}
                      >
                        <Td className="font-mono text-zinc-300">
                          {String(r.model).split(":").pop()}
                        </Td>
                        <Td className="text-zinc-500">{String(r.phase).replace(/_/g, " ")}</Td>
                        <Td align="right" className="tabular-nums text-zinc-400">{r.calls}</Td>
                        <Td align="right" className="tabular-nums text-zinc-400">
                          {Number(r.tokens_in).toLocaleString()}
                        </Td>
                        <Td align="right" className="tabular-nums text-zinc-400">
                          {Number(r.tokens_out).toLocaleString()}
                        </Td>
                        <Td align="right" className="tabular-nums text-zinc-500">
                          {r.avg_latency_ms != null ? `${Math.round(Number(r.avg_latency_ms))}ms` : "--"}
                        </Td>
                        <Td align="right" className="tabular-nums font-mono font-semibold text-emerald-400">
                          ${Number(r.cost_usd).toFixed(4)}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shared table primitives
// ---------------------------------------------------------------------------

function Th({ children, align }: { children: React.ReactNode; align?: "right" }) {
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
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

function EmptyState({ icon: Icon, msg }: { icon: React.ElementType; msg: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-2 text-center">
      <Icon className="h-8 w-8 text-zinc-700" />
      <p className="text-zinc-600 text-sm">{msg}</p>
    </div>
  )
}

function FetchError({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 gap-3 text-center px-6">
      <AlertTriangle className="h-8 w-8 text-red-500/60" />
      <p className="text-red-400 text-sm">{msg}</p>
      <Button
        size="sm"
        variant="outline"
        onClick={onRetry}
        className="border-zinc-700 text-zinc-400 hover:text-zinc-200 h-7 text-xs"
      >
        Retry
      </Button>
    </div>
  )
}
