import { useState, useEffect, useMemo } from "react"
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

interface MetricTileProps {
  icon: React.ElementType
  label: string
  value: string
  sub?: string
  iconClass?: string
}

function MetricTile({ icon: Icon, label, value, sub, iconClass }: MetricTileProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon className={cn("h-4 w-4", iconClass ?? "text-zinc-500")} />
        <span className="text-xs text-zinc-500 font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white tabular-nums font-mono">{value}</div>
      {sub && <div className="text-xs text-zinc-600 mt-1">{sub}</div>}
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

const PHASE_COLORS: Record<string, string> = {
  phase_2_search: "#3b82f6",
  phase_3_screening: "#8b5cf6",
  phase_4_extraction: "#f59e0b",
  phase_5_synthesis: "#10b981",
  phase_6_writing: "#ef4444",
  phase_unknown: "#6b7280",
}

function phaseColor(phase: string): string {
  for (const [key, color] of Object.entries(PHASE_COLORS)) {
    if (phase.includes(key.replace("phase_", "").split("_")[1])) return color
  }
  return "#8b5cf6"
}

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  dbIsDone?: boolean
}

export function CostView({ costStats, dbRunId, dbIsDone = false }: CostViewProps) {
  const [dbRows, setDbRows] = useState<DbCostRow[]>([])
  const [dbTotalCost, setDbTotalCost] = useState(0)

  // When browsing a completed historical run with no live SSE costs, load from DB.
  useEffect(() => {
    if (!dbIsDone || !dbRunId || costStats.total_calls > 0) return
    fetchDbCosts(dbRunId)
      .then((d) => { setDbRows(d.records); setDbTotalCost(d.total_cost) })
      .catch(() => {})
  }, [dbIsDone, dbRunId, costStats.total_calls])

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

  const chartData = by_phase.map((p) => ({
    name: p.phase.replace("phase_", "").replace(/_/g, " "),
    cost: parseFloat(p.cost_usd.toFixed(6)),
    fullPhase: p.phase,
  }))

  const hasCosts = total_calls > 0

  if (!hasCosts) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <DollarSign className="h-10 w-10 text-zinc-700 mb-3" />
        <p className="text-zinc-500 text-sm">Cost data will appear once the review starts.</p>
      </div>
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

      {/* Cost by phase chart */}
      {chartData.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-zinc-300 mb-4">Cost by Phase</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chartData} margin={{ left: -20, right: 10 }}>
              <XAxis
                dataKey="name"
                tick={{ fill: "#71717a", fontSize: 11 }}
                axisLine={{ stroke: "#27272a" }}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                tick={{ fill: "#71717a", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "#27272a" }} />
              <Bar dataKey="cost" radius={[4, 4, 0, 0]}>
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
      )}

      {/* Cost by model table */}
      {by_model.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Model</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Model</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Calls</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Tokens In</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Tokens Out</th>
                  <th className="text-right px-5 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Cost</th>
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

      {/* Phase breakdown table */}
      {by_phase.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-zinc-800">
            <h3 className="text-sm font-semibold text-zinc-300">Cost by Phase</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800">
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Phase</th>
                  <th className="text-right px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Calls</th>
                  <th className="text-right px-5 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide">Cost</th>
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
                      {p.phase.replace(/_/g, " ")}
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
