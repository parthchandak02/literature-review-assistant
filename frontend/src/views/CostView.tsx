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
import { fetchDbCosts } from "@/lib/api"
import type { DbCostRow } from "@/lib/api"
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

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
}

export function CostView({ costStats, dbRunId }: CostViewProps) {
  const [dbRows, setDbRows] = useState<DbCostRow[]>([])
  const [dbTotalCost, setDbTotalCost] = useState(0)
  const [loadingDb, setLoadingDb] = useState(false)
  const [dbError, setDbError] = useState<string | null>(null)

  const loadDbCosts = useCallback(() => {
    if (!dbRunId || costStats.total_calls > 0) return
    setLoadingDb(true)
    setDbError(null)
    fetchDbCosts(dbRunId)
      .then((d) => { setDbRows(d.records); setDbTotalCost(d.total_cost) })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        setDbError(
          msg.toLowerCase().includes("failed to fetch")
            ? "Cannot reach backend."
            : msg,
        )
      })
      .finally(() => setLoadingDb(false))
  }, [dbRunId, costStats.total_calls])

  // When browsing a completed historical run with no live SSE costs, load from DB.
  useEffect(() => {
    loadDbCosts()
  }, [loadDbCosts])

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

  // Live SSE data takes priority; fall back to DB aggregation for historical runs.
  const activeCostStats = costStats.total_calls > 0 ? costStats : (dbCostStats ?? costStats)

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
          <div className="px-5 py-3 border-b border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Model</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
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
          <div className="px-5 py-3 border-b border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Phase</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
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
    </div>
  )
}
