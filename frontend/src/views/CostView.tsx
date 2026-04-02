import { useState, useEffect, useMemo, useCallback } from "react"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts"
import { DollarSign, Zap, ArrowUpDown, Activity } from "lucide-react"
import { cn } from "@/lib/utils"
import { fetchDbCostAggregates, fetchDbCosts, fetchWorkflowValidationSummary, getDbCostExportUrl } from "@/lib/api"
import type {
  DbCostAggregatesResponse,
  DbCostExportGranularity,
  DbCostRow,
  ScreeningDiagnostics,
  ValidationSummary,
} from "@/lib/api"
import type { CostStats, ModelStat, PhaseStat } from "@/hooks/useCostStats"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { SkeletonCard } from "@/components/ui/skeleton"
import { PHASE_LABEL_MAP, phaseColor } from "@/lib/constants"

interface MetricTileProps {
  icon: React.ElementType
  label: string
  value: string
  sub?: string
  iconClass?: string
}

function MetricTile({ icon: Icon, label, value, sub, iconClass }: MetricTileProps) {
  return (
    <div className="card-section">
      <div className="flex items-center gap-2 mb-3">
        <Icon className={cn("h-4 w-4", iconClass ?? "text-zinc-500")} />
        <span className="label-caps">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white tabular-nums font-mono">{value}</div>
      {sub && <div className="label-muted mt-1">{sub}</div>}
    </div>
  )
}

// Custom dark tooltip for recharts
function DarkTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-xs">
      <div className="text-zinc-400 mb-1">{label}</div>
      <div className="text-white font-mono font-semibold">${payload[0].value.toFixed(4)}</div>
    </div>
  )
}

function formatPhaseName(phase: string): string {
  if (phase in PHASE_LABEL_MAP) return PHASE_LABEL_MAP[phase]
  // Generic fallback: strip phase_N_ or quality_ prefix, title-case words
  return phase
    .replace(/^phase_\d+_/, "")
    .replace(/^quality_/, "")
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

function formatUsd(value: number): string {
  return `$${value.toFixed(4)}`
}

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  workflowId?: string | null
  isLive?: boolean
}

export function CostView({ costStats, dbRunId, workflowId, isLive }: CostViewProps) {
  const [dbRows, setDbRows] = useState<DbCostRow[]>([])
  const [dbTotalCost, setDbTotalCost] = useState(0)
  const [screeningDiagnostics, setScreeningDiagnostics] = useState<ScreeningDiagnostics | null>(null)
  const [validationSummary, setValidationSummary] = useState<ValidationSummary["latest_run"] | null>(null)
  const [loadingDb, setLoadingDb] = useState(false)
  const [dbError, setDbError] = useState<string | null>(null)
  const [opsAggregates, setOpsAggregates] = useState<DbCostAggregatesResponse | null>(null)
  const [opsLoading, setOpsLoading] = useState(false)
  const [opsError, setOpsError] = useState<string | null>(null)
  const [opsStartDate, setOpsStartDate] = useState("")
  const [opsEndDate, setOpsEndDate] = useState("")
  const [opsGranularity, setOpsGranularity] = useState<DbCostExportGranularity>("day")

  const opsEnabled = useMemo(() => {
    if (typeof window === "undefined") return false
    const q = new URLSearchParams(window.location.search)
    return q.get("ops") === "1"
  }, [])

  const loadDbCosts = useCallback(() => {
    if (!dbRunId) return
    // Only show the loading skeleton on the very first fetch (no rows yet).
    if (!dbRows.length) setLoadingDb(true)
    setDbError(null)
    fetchDbCosts(dbRunId)
      .then((d) => {
        setDbRows(d.records)
        setDbTotalCost(d.total_cost)
        setScreeningDiagnostics(d.screening_diagnostics ?? null)
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        setDbError(
          msg.toLowerCase().includes("failed to fetch")
            ? "Cannot reach backend."
            : msg,
        )
      })
      .finally(() => setLoadingDb(false))
  }, [dbRunId, dbRows.length])

  useEffect(() => {
    if (!workflowId) return
    fetchWorkflowValidationSummary(workflowId)
      .then((res) => setValidationSummary(res.latest_run))
      .catch(() => setValidationSummary(null))
  }, [workflowId])

  // Always load from DB on mount, and poll every 5 s while the run is active
  // so costs from all phases (screening, extraction, writing, etc.) stay accurate.
  // Previously the DB was skipped whenever SSE had any events, which caused
  // earlier phase costs to disappear once the writing phase started streaming.
  useEffect(() => {
     
    loadDbCosts()
  }, [loadDbCosts])

  useEffect(() => {
    if (!isLive || !dbRunId) return
    const id = setInterval(loadDbCosts, 5000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadDbCosts identity changes on dbRows.length; use stable refs via interval
  }, [isLive, dbRunId])

  const loadOpsAggregates = useCallback(() => {
    if (!dbRunId || !opsEnabled) return
    setOpsLoading(true)
    setOpsError(null)
    fetchDbCostAggregates(dbRunId, {
      start_ts: opsStartDate || undefined,
      end_ts: opsEndDate || undefined,
    })
      .then((data) => setOpsAggregates(data))
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        setOpsError(msg)
      })
      .finally(() => setOpsLoading(false))
  }, [dbRunId, opsEnabled, opsStartDate, opsEndDate])

  useEffect(() => {
    if (!opsEnabled || !dbRunId) return
    loadOpsAggregates()
  }, [opsEnabled, dbRunId, loadOpsAggregates])

  // Aggregate DbCostRow[] into the same CostStats shape the rendering already uses.
  const dbCostStats = useMemo<CostStats | null>(() => {
    if (!dbRows.length) return null
    const modelMap: Record<string, ModelStat> = {}
    const phaseMap: Record<string, PhaseStat> = {}
    let total_tokens_in = 0
    let total_tokens_out = 0
    let total_calls = 0
    for (const r of dbRows) {
      total_tokens_in += Number(r.tokens_in)
      total_tokens_out += Number(r.tokens_out)
      total_calls += Number(r.calls)
      if (!modelMap[r.model]) {
        modelMap[r.model] = { model: r.model, calls: 0, tokens_in: 0, tokens_out: 0, cost_usd: 0 }
      }
      modelMap[r.model].calls += Number(r.calls)
      modelMap[r.model].tokens_in += Number(r.tokens_in)
      modelMap[r.model].tokens_out += Number(r.tokens_out)
      modelMap[r.model].cost_usd += Number(r.cost_usd)
      if (!phaseMap[r.phase]) {
        phaseMap[r.phase] = { phase: r.phase, cost_usd: 0, calls: 0 }
      }
      phaseMap[r.phase].cost_usd += Number(r.cost_usd)
      phaseMap[r.phase].calls += Number(r.calls)
    }
    return {
      total_cost: dbTotalCost,
      total_tokens_in,
      total_tokens_out,
      total_calls,
      by_model: Object.values(modelMap).sort((a, b) => b.cost_usd - a.cost_usd),
      by_phase: Object.values(phaseMap).sort((a, b) => b.cost_usd - a.cost_usd),
    }
  }, [dbRows, dbTotalCost])

  // DB data is always the primary source -- it captures every LLM call across
  // all phases regardless of whether the SSE event was buffered in event_log.
  // SSE-derived stats are only used as a last resort when the DB hasn't been
  // queried yet (e.g., before the first poll completes).
  const activeCostStats = dbCostStats ?? (costStats.total_calls > 0 ? costStats : costStats)

  const { total_cost, total_tokens_in, total_tokens_out, total_calls, by_model, by_phase } = activeCostStats

  const chartData = by_phase
    .slice()
    .sort((a, b) => b.cost_usd - a.cost_usd)
    .map((p) => ({
      name: formatPhaseName(p.phase),
      cost: parseFloat(p.cost_usd.toFixed(6)),
      fullPhase: p.phase,
    }))

  const nonZeroPhasesCount = chartData.filter((d) => d.cost > 0).length

  const hasCosts = total_calls > 0 || total_cost > 0
  const opsExportUrl = dbRunId
    ? getDbCostExportUrl(dbRunId, {
      start_ts: opsStartDate || undefined,
      end_ts: opsEndDate || undefined,
      granularity: opsGranularity,
    })
    : ""

  if (loadingDb) {
    return (
      <div className="flex flex-col gap-4 max-w-4xl">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
        </div>
        <SkeletonCard />
      </div>
    )
  }

  if (dbError) {
    return (
      <FetchError
        message={dbError}
        onRetry={loadDbCosts}
        className="max-w-md"
      />
    )
  }

  if (!hasCosts) {
    return (
      <EmptyState
        icon={DollarSign}
        heading="Cost data will appear once the review starts."
        className="h-64"
      />
    )
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      {/* Top metric tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricTile
          icon={DollarSign}
          label="Total Cost"
          value={`$${total_cost.toFixed(4)}`}
          sub="across all agents"
          iconClass="text-emerald-400"
        />
        <MetricTile
          icon={Activity}
          label="LLM Calls"
          value={String(total_calls)}
          sub="successful completions"
          iconClass="text-violet-400"
        />
        <MetricTile
          icon={Zap}
          label="Tokens In"
          value={total_tokens_in.toLocaleString()}
          sub="prompt tokens"
          iconClass="text-blue-400"
        />
        <MetricTile
          icon={ArrowUpDown}
          label="Tokens Out"
          value={total_tokens_out.toLocaleString()}
          sub="completion tokens"
          iconClass="text-amber-400"
        />
      </div>

      {/* Cost by phase chart -- horizontal bars so labels have room.
          Only shown when 2+ phases have non-zero cost; a single bar is misleading. */}
      {nonZeroPhasesCount >= 2 ? (
        <div className="card-surface p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4">Cost by Phase</h3>
          <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 36)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 4, right: 56, top: 4, bottom: 4 }}
            >
              <XAxis
                type="number"
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                tick={{ fill: "#71717a", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={110}
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "#27272a55" }} />
              <Bar dataKey="cost" radius={[0, 4, 4, 0]} label={{ position: "right", formatter: (v: unknown) => `$${(v as number).toFixed(4)}`, fill: "#52525b", fontSize: 10 }}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.fullPhase}
                    fill={phaseColor(entry.fullPhase)}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : chartData.length > 0 ? (
        <div className="card-surface p-5 flex items-center justify-center h-24">
          <p className="label-muted">Cost breakdown will appear as phases complete.</p>
        </div>
      ) : null}

      {/* Cost by model table */}
      {by_model.length > 0 && (
        <div className="card-surface overflow-hidden">
          <div className="glass-toolbar px-5 py-3 border-b border-zinc-800/70">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Model</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="glass-toolbar border-b border-zinc-800/70">
                  <th className="text-left px-5 py-2.5 label-caps">Model</th>
                  <th className="text-right px-4 py-2.5 label-caps">Calls</th>
                  <th className="text-right px-4 py-2.5 label-caps">Tokens In</th>
                  <th className="text-right px-4 py-2.5 label-caps">Tokens Out</th>
                  <th className="text-right px-5 py-2.5 label-caps">Cost</th>
                </tr>
              </thead>
              <tbody>
                {by_model.map((m, i) => (
                  <tr
                    key={m.model}
                    className={cn(
                      "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                      i === by_model.length - 1 && "border-0",
                    )}
                  >
                    <td className="px-5 py-3 font-mono text-xs text-zinc-300">
                      {m.model.split(":").pop() ?? m.model}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-zinc-400 text-xs">{m.calls}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-zinc-400 text-xs">
                      {m.tokens_in.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-zinc-400 text-xs">
                      {m.tokens_out.toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums font-mono font-medium text-emerald-400 text-xs">
                      ${m.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cost by phase table */}
      {by_phase.length > 0 && (
        <div className="card-surface overflow-hidden">
          <div className="glass-toolbar px-5 py-3 border-b border-zinc-800/70">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Phase</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="glass-toolbar border-b border-zinc-800/70">
                  <th className="text-left px-5 py-2.5 label-caps">Phase</th>
                  <th className="text-right px-4 py-2.5 label-caps">Calls</th>
                  <th className="text-right px-5 py-2.5 label-caps">Cost</th>
                </tr>
              </thead>
              <tbody>
                {by_phase.map((p, i) => (
                  <tr
                    key={p.phase}
                    className={cn(
                      "border-b border-zinc-800/50 hover:bg-zinc-800/40 transition-colors",
                      i === by_phase.length - 1 && "border-0",
                    )}
                  >
                    <td className="px-5 py-3 text-zinc-300 text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 rounded-sm shrink-0"
                          style={{ backgroundColor: phaseColor(p.phase), opacity: 0.85 }}
                        />
                        {formatPhaseName(p.phase)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-zinc-400 text-xs">{p.calls}</td>
                    <td className="px-5 py-3 text-right tabular-nums font-mono font-medium text-emerald-400 text-xs">
                      ${p.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {opsEnabled && dbRunId && (
        <div className="card-surface overflow-hidden">
          <div className="glass-toolbar px-5 py-3 border-b border-zinc-800/70 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-zinc-300">Ops Cost Diagnostics</h3>
            <div className="label-muted">Hidden mode (`ops=1`)</div>
          </div>
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <label className="flex flex-col gap-1 text-xs text-zinc-400">
                Start
                <input
                  type="date"
                  value={opsStartDate}
                  onChange={(e) => setOpsStartDate(e.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-zinc-200"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-zinc-400">
                End
                <input
                  type="date"
                  value={opsEndDate}
                  onChange={(e) => setOpsEndDate(e.target.value)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-zinc-200"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-zinc-400">
                CSV Bucket
                <select
                  value={opsGranularity}
                  onChange={(e) => setOpsGranularity(e.target.value as DbCostExportGranularity)}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-900 px-2 text-zinc-200"
                >
                  <option value="day">day</option>
                  <option value="week">week</option>
                  <option value="month">month</option>
                </select>
              </label>
              <div className="flex items-end gap-2 md:col-span-2">
                <button
                  type="button"
                  onClick={loadOpsAggregates}
                  className="h-9 px-3 rounded-md border border-zinc-700 bg-zinc-900 text-zinc-200 text-xs hover:bg-zinc-800"
                >
                  Refresh
                </button>
                <a
                  href={opsExportUrl}
                  className="h-9 px-3 rounded-md border border-zinc-700 bg-zinc-900 text-zinc-200 text-xs hover:bg-zinc-800 inline-flex items-center"
                >
                  Export CSV
                </a>
              </div>
            </div>

            {opsLoading && <div className="text-xs text-zinc-500">Loading ops aggregates...</div>}
            {opsError && <div className="text-xs text-rose-400">{opsError}</div>}

            {opsAggregates?.totals && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="text-zinc-400">Total cost: <span className="text-zinc-200 font-mono">{formatUsd(Number(opsAggregates.totals.total_cost_usd || 0))}</span></div>
                <div className="text-zinc-400">Calls: <span className="text-zinc-200 font-mono">{Number(opsAggregates.totals.total_calls || 0)}</span></div>
                <div className="text-zinc-400">Tokens in: <span className="text-zinc-200 font-mono">{Number(opsAggregates.totals.total_tokens_in || 0).toLocaleString()}</span></div>
                <div className="text-zinc-400">Tokens out: <span className="text-zinc-200 font-mono">{Number(opsAggregates.totals.total_tokens_out || 0).toLocaleString()}</span></div>
              </div>
            )}

            {opsAggregates && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="rounded-md border border-zinc-800 p-3">
                  <div className="text-zinc-400 mb-2">Top phases</div>
                  {opsAggregates.by_phase.slice(0, 5).map((row) => (
                    <div key={row.group_key} className="flex items-center justify-between py-1 text-zinc-300">
                      <span>{formatPhaseName(row.group_key)}</span>
                      <span className="font-mono">{formatUsd(Number(row.cost_usd))}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-md border border-zinc-800 p-3">
                  <div className="text-zinc-400 mb-2">Top models</div>
                  {opsAggregates.by_model.slice(0, 5).map((row) => (
                    <div key={row.group_key} className="flex items-center justify-between py-1 text-zinc-300">
                      <span>{row.group_key}</span>
                      <span className="font-mono">{formatUsd(Number(row.cost_usd))}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-md border border-zinc-800 p-3">
                  <div className="text-zinc-400 mb-2">Recent buckets</div>
                  {opsAggregates.by_day.slice(-5).map((row) => (
                    <div key={row.bucket} className="flex items-center justify-between py-1 text-zinc-300">
                      <span>{row.bucket}</span>
                      <span className="font-mono">{formatUsd(Number(row.cost_usd))}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {(screeningDiagnostics || validationSummary) && (
        <div className="card-surface overflow-hidden">
          <div className="glass-toolbar px-5 py-3 border-b border-zinc-800/70">
            <h3 className="text-sm font-semibold text-zinc-300">Validation and Screening Diagnostics</h3>
          </div>
          <div className="p-5 space-y-3 text-xs text-zinc-300">
            {validationSummary && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div>Validation status: <span className="font-semibold">{validationSummary.status}</span></div>
                <div>Profile: <span className="font-semibold">{validationSummary.profile}</span></div>
                <div>Error checks: <span className="font-semibold">{validationSummary.error_count}</span></div>
                <div>Warn checks: <span className="font-semibold">{validationSummary.warn_count}</span></div>
              </div>
            )}
            {screeningDiagnostics && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-zinc-400">
                <div>Batch parse degraded: {screeningDiagnostics.batch_parse_degraded}</div>
                <div>Batch id mismatch: {screeningDiagnostics.batch_id_mismatch}</div>
                <div>Missing fallback: {screeningDiagnostics.batch_missing_fallback}</div>
                <div>Contract violations: {screeningDiagnostics.contract_violation_count}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
