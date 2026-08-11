import { useMemo, useState } from "react"
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
import { CHART_THEME } from "@/lib/constants"
import { getDbCostExportUrl } from "@/lib/api"
import type {
  CostDashboardResponse,
  DbCostExportGranularity,
} from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import {
  costsFetchErrorMessage,
  useDbCostAggregates,
  useDbCostDashboard,
  useWorkflowValidationSummaryWithChecks,
} from "@/hooks/useDbCosts"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { SkeletonCard } from "@/components/ui/skeleton"
import { ViewToolbar } from "@/components/ui/view-toolbar"
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
        <Icon className={cn("h-4 w-4", iconClass ?? "text-muted")} />
        <span className="label-caps">{label}</span>
      </div>
      <div className="text-2xl font-bold text-foreground tabular-nums font-mono">{value}</div>
      {sub && <div className="label-muted mt-1">{sub}</div>}
    </div>
  )
}

function CostChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
      <div className="text-muted mb-1">{label}</div>
      <div className="text-foreground font-mono font-semibold">${payload[0].value.toFixed(4)}</div>
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

function buildCostStatsFromDashboard(dashboard: CostDashboardResponse): CostStats {
  return {
    total_cost: dashboard.total_cost ?? dashboard.totals.cost_usd,
    total_tokens_in: dashboard.totals.tokens_in,
    total_tokens_out: dashboard.totals.tokens_out,
    total_calls: dashboard.totals.calls,
    by_model: dashboard.by_model.map((m) => ({
      model: m.model,
      calls: m.calls,
      tokens_in: m.tokens_in,
      tokens_out: m.tokens_out,
      cost_usd: m.cost_usd,
    })),
    by_phase: dashboard.by_phase.map((p) => ({
      phase: p.phase,
      cost_usd: p.cost_usd,
      calls: p.calls,
    })),
  }
}

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  workflowId?: string | null
  isLive?: boolean
}

export function CostView({ costStats, dbRunId, workflowId, isLive }: CostViewProps) {
  const [opsStartDate, setOpsStartDate] = useState("")
  const [opsEndDate, setOpsEndDate] = useState("")
  const [opsGranularity, setOpsGranularity] = useState<DbCostExportGranularity>("day")

  const opsEnabled = useMemo(() => {
    if (typeof window === "undefined") return false
    const q = new URLSearchParams(window.location.search)
    return q.get("ops") === "1"
  }, [])

  const dashboardQuery = useDbCostDashboard(dbRunId, { enabled: Boolean(dbRunId), isLive })
  const validationQuery = useWorkflowValidationSummaryWithChecks(workflowId)
  const validationSummary = validationQuery.data?.latest_run ?? null

  const opsAggregatesQuery = useDbCostAggregates(dbRunId, {
    enabled: opsEnabled && Boolean(dbRunId),
    startDate: opsStartDate,
    endDate: opsEndDate,
    granularity: opsGranularity,
  })

  const dbCostStats = useMemo(() => {
    const dashboard = dashboardQuery.data
    if (!dashboard) return null
    const hasData = dashboard.totals.calls > 0 || dashboard.totals.cost_usd > 0
    if (!hasData) return null
    return buildCostStatsFromDashboard(dashboard)
  }, [dashboardQuery.data])

  const screeningDiagnostics = dashboardQuery.data?.screening_diagnostics ?? null
  const validationChecks = validationQuery.data?.checks ?? []
  const loadingDb = dashboardQuery.isLoading
  const dbError = dashboardQuery.isError ? costsFetchErrorMessage(dashboardQuery.error) : null
  const opsAggregates = opsAggregatesQuery.data ?? null
  const opsLoading = opsAggregatesQuery.isFetching
  const opsError = opsAggregatesQuery.isError
    ? opsAggregatesQuery.error instanceof Error
      ? opsAggregatesQuery.error.message
      : String(opsAggregatesQuery.error)
    : null

  // DB data is always the primary source -- it captures every LLM call across
  // all phases regardless of whether the SSE event was buffered in event_log.
  // SSE-derived stats are only used as a last resort when the DB hasn't been
  // queried yet (e.g., before the first poll completes).
  const activeCostStats = dbCostStats ?? costStats

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
        onRetry={() => { void dashboardQuery.refetch() }}
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
          iconClass="text-intent-success"
        />
        <MetricTile
          icon={Activity}
          label="LLM Calls"
          value={String(total_calls)}
          sub="successful completions"
          iconClass="text-intent-primary"
        />
        <MetricTile
          icon={Zap}
          label="Tokens In"
          value={total_tokens_in.toLocaleString()}
          sub="prompt tokens"
          iconClass="text-intent-info"
        />
        <MetricTile
          icon={ArrowUpDown}
          label="Tokens Out"
          value={total_tokens_out.toLocaleString()}
          sub="completion tokens"
          iconClass="text-intent-warning"
        />
      </div>

      {/* Cost by phase chart -- horizontal bars so labels have room.
          Only shown when 2+ phases have non-zero cost; a single bar is misleading. */}
      {nonZeroPhasesCount >= 2 ? (
        <div className="card-surface p-5">
          <h3 className="text-sm font-semibold text-foreground mb-4">Cost by Phase</h3>
          <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 36)}>
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ left: 4, right: 56, top: 4, bottom: 4 }}
            >
              <XAxis
                type="number"
                tickFormatter={(v: number) => `$${v.toFixed(3)}`}
                tick={{ fill: CHART_THEME.tickFill, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={110}
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CostChartTooltip />} cursor={{ fill: CHART_THEME.cursorFill }} />
              <Bar dataKey="cost" radius={[0, 4, 4, 0]} label={{ position: "right", formatter: (v: unknown) => `$${(v as number).toFixed(4)}`, fill: "var(--color-muted-foreground)", fontSize: 10 }}>
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
          <ViewToolbar
            dense
            title={<h3 className="text-sm font-semibold text-foreground">Cost by Model</h3>}
          />
          <div className="data-surface overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
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
                      "border-b border-border/50 hover:bg-surface-2/40 transition-colors",
                      i === by_model.length - 1 && "border-0",
                    )}
                  >
                    <td className="px-5 py-3 font-mono text-xs text-foreground">
                      {m.model.split(":").pop() ?? m.model}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted text-xs">{m.calls}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted text-xs">
                      {m.tokens_in.toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted text-xs">
                      {m.tokens_out.toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-right tabular-nums font-mono font-medium text-intent-success text-xs">
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
          <ViewToolbar
            dense
            title={<h3 className="text-sm font-semibold text-foreground">Cost by Phase</h3>}
          />
          <div className="data-surface overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
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
                      "border-b border-border/50 hover:bg-surface-2/40 transition-colors",
                      i === by_phase.length - 1 && "border-0",
                    )}
                  >
                    <td className="px-5 py-3 text-foreground text-xs">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 rounded-sm shrink-0"
                          style={{ backgroundColor: phaseColor(p.phase), opacity: 0.85 }}
                        />
                        {formatPhaseName(p.phase)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted text-xs">{p.calls}</td>
                    <td className="px-5 py-3 text-right tabular-nums font-mono font-medium text-intent-success text-xs">
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
          <ViewToolbar
            dense
            title={<h3 className="text-sm font-semibold text-foreground">Ops Cost Diagnostics</h3>}
            actions={<div className="label-muted">Hidden mode (`ops=1`)</div>}
          />
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted">
                Start
                <input
                  type="date"
                  value={opsStartDate}
                  onChange={(e) => setOpsStartDate(e.target.value)}
                  className="h-9 rounded-md border border-border bg-surface-2 px-2 text-foreground"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted">
                End
                <input
                  type="date"
                  value={opsEndDate}
                  onChange={(e) => setOpsEndDate(e.target.value)}
                  className="h-9 rounded-md border border-border bg-surface-2 px-2 text-foreground"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs text-muted">
                CSV Bucket
                <select
                  value={opsGranularity}
                  onChange={(e) => setOpsGranularity(e.target.value as DbCostExportGranularity)}
                  className="h-9 rounded-md border border-border bg-surface-2 px-2 text-foreground"
                >
                  <option value="day">day</option>
                  <option value="week">week</option>
                  <option value="month">month</option>
                </select>
              </label>
              <div className="flex items-end gap-2 md:col-span-2">
                <button
                  type="button"
                  onClick={() => { void opsAggregatesQuery.refetch() }}
                  className="h-9 px-3 rounded-md border border-border bg-surface-2 text-foreground text-xs hover:bg-surface-3"
                >
                  Refresh
                </button>
                <a
                  href={opsExportUrl}
                  className="h-9 px-3 rounded-md border border-border bg-surface-2 text-foreground text-xs hover:bg-surface-3 inline-flex items-center"
                >
                  Export CSV
                </a>
              </div>
            </div>

            {opsLoading && <div className="text-xs text-muted">Loading ops aggregates...</div>}
            {opsError && <div className="text-xs text-intent-danger">{opsError}</div>}

            {opsAggregates?.totals && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="text-muted">Total cost: <span className="text-foreground font-mono">{formatUsd(Number(opsAggregates.totals.total_cost_usd || 0))}</span></div>
                <div className="text-muted">Calls: <span className="text-foreground font-mono">{Number(opsAggregates.totals.total_calls || 0)}</span></div>
                <div className="text-muted">Tokens in: <span className="text-foreground font-mono">{Number(opsAggregates.totals.total_tokens_in || 0).toLocaleString()}</span></div>
                <div className="text-muted">Tokens out: <span className="text-foreground font-mono">{Number(opsAggregates.totals.total_tokens_out || 0).toLocaleString()}</span></div>
              </div>
            )}

            {opsAggregates && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                <div className="rounded-md border border-border p-3">
                  <div className="text-muted mb-2">Top phases</div>
                  {opsAggregates.by_phase.slice(0, 5).map((row) => (
                    <div key={row.group_key} className="flex items-center justify-between py-1 text-foreground">
                      <span>{formatPhaseName(row.group_key)}</span>
                      <span className="font-mono">{formatUsd(Number(row.cost_usd))}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-md border border-border p-3">
                  <div className="text-muted mb-2">Top models</div>
                  {opsAggregates.by_model.slice(0, 5).map((row) => (
                    <div key={row.group_key} className="flex items-center justify-between py-1 text-foreground">
                      <span>{row.group_key}</span>
                      <span className="font-mono">{formatUsd(Number(row.cost_usd))}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-md border border-border p-3">
                  <div className="text-muted mb-2">Recent buckets</div>
                  {opsAggregates.by_day.slice(-5).map((row) => (
                    <div key={row.bucket} className="flex items-center justify-between py-1 text-foreground">
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
          <ViewToolbar
            dense
            title={
              <h3 className="text-sm font-semibold text-foreground">
                Validation and Screening Diagnostics
              </h3>
            }
          />
          <div className="p-5 space-y-3 text-xs text-foreground">
            {validationSummary && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <div>Validation status: <span className="font-semibold">{validationSummary.status}</span></div>
                <div>Profile: <span className="font-semibold">{validationSummary.profile}</span></div>
                <div>Error checks: <span className="font-semibold">{validationSummary.error_count}</span></div>
                <div>Warn checks: <span className="font-semibold">{validationSummary.warn_count}</span></div>
              </div>
            )}
            {validationChecks.length > 0 && (
              <div className="rounded-xl border border-border bg-card/70 overflow-hidden">
                <div className="px-3 py-2 border-b border-border text-xs font-semibold text-muted">
                  Latest validation checks
                </div>
                <div className="divide-y divide-border">
                  {validationChecks.slice(0, 8).map((check, idx) => (
                    <div key={`${check.phase}-${check.check_name}-${idx}`} className="px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-foreground">{check.check_name}</div>
                        <div className={cn(
                          "font-medium",
                          check.status === "error" ? "text-intent-danger" : check.status === "warn" ? "text-intent-warning" : "text-intent-success",
                        )}>
                          {check.status}
                        </div>
                      </div>
                      <div className="mt-0.5 text-muted">
                        {check.phase}
                        {check.metric_value != null ? ` | metric ${check.metric_value}` : ""}
                        {check.source_module ? ` | ${check.source_module}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {screeningDiagnostics && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-muted">
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
