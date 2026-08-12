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
import { DollarSign, Zap, ArrowUpDown, Activity, BarChart3 } from "lucide-react"
import { cn } from "@/lib/utils"
import { CHART_THEME } from "@/lib/constants"
import { getDbCostExportUrl } from "@/lib/api"
import { buildCostStatsFromDashboard, type CostStats } from "@/hooks/useCostStats"
import {
  costsFetchErrorMessage,
  useDbCostAggregates,
  useDbCostDashboard,
  useWorkflowValidationSummaryWithChecks,
} from "@/hooks/useDbCosts"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { SkeletonCard } from "@/components/ui/skeleton"
import { PageSection } from "@/components/ui/section"
import { ChartTableToggle, type ChartTableMode } from "@/components/cost-ops/ChartTableToggle"
import { CostChartTooltip } from "@/components/cost-ops/CostChartTooltip"
import { CostOpsFiltersBar } from "@/components/cost-ops/CostOpsFiltersBar"
import {
  CostOpsGroupSection,
  CostOpsPhaseSection,
  CostOpsSpendSection,
  CostsLoadingState,
} from "@/components/cost-ops/CostOpsChartSection"
import {
  buildPresetRange,
  costOpsGridClass,
  formatInteger,
  formatPhaseName,
  formatUsd,
  statCardClass,
  toApiEnd,
  toApiStart,
} from "@/components/cost-ops/costOpsFormatters"
import { phaseColor } from "@/lib/constants"

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

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  workflowId?: string | null
  isLive?: boolean
  isSSEConnected?: boolean
}

export function CostView({ costStats, dbRunId, workflowId, isLive, isSSEConnected }: CostViewProps) {
  const defaultOpsRange = useMemo(() => buildPresetRange(30), [])
  const [opsStartDate, setOpsStartDate] = useState(defaultOpsRange.startDate)
  const [opsEndDate, setOpsEndDate] = useState(defaultOpsRange.endDate)
  const [opsPreset, setOpsPreset] = useState<"5d" | "30d" | "90d" | "custom">("30d")
  const [opsViewMode, setOpsViewMode] = useState<ChartTableMode>("table")
  const [phaseViewMode, setPhaseViewMode] = useState<ChartTableMode>("chart")

  function applyOpsPreset(nextPreset: "5d" | "30d" | "90d") {
    const days = nextPreset === "5d" ? 5 : nextPreset === "30d" ? 30 : 90
    const range = buildPresetRange(days)
    setOpsPreset(nextPreset)
    setOpsStartDate(range.startDate)
    setOpsEndDate(range.endDate)
  }

  const opsEnabled = useMemo(() => {
    if (typeof window === "undefined") return false
    const q = new URLSearchParams(window.location.search)
    return q.get("ops") === "1"
  }, [])

  const dashboardQuery = useDbCostDashboard(dbRunId, {
    enabled: Boolean(dbRunId),
    isLive,
    isSSEConnected,
  })
  const validationQuery = useWorkflowValidationSummaryWithChecks(workflowId)
  const validationSummary = validationQuery.data?.latest_run ?? null

  const opsAggregatesQuery = useDbCostAggregates(dbRunId, {
    enabled: opsEnabled && Boolean(dbRunId),
    startDate: opsStartDate,
    endDate: opsEndDate,
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
      start_ts: toApiStart(opsStartDate),
      end_ts: toApiEnd(opsEndDate),
      granularity: "day",
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

      {/* Cost by phase — chart or table, never both */}
      {by_phase.length > 0 && (
        <PageSection
          icon={BarChart3}
          title="Cost by Phase"
          action={
            <ChartTableToggle mode={phaseViewMode} onChange={setPhaseViewMode} />
          }
          contentClassName={phaseViewMode === "table" ? "p-0" : undefined}
        >
          {phaseViewMode === "chart" ? (
            nonZeroPhasesCount >= 2 ? (
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
            ) : (
              <p className="label-muted text-center py-4">
                Cost breakdown will appear as phases complete.
              </p>
            )
          ) : (
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
          )}
        </PageSection>
      )}

      {/* Cost by model table */}
      {by_model.length > 0 && (
        <PageSection title="Cost by Model" contentClassName="p-0">
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
        </PageSection>
      )}

      {opsEnabled && dbRunId && (
        <PageSection
          title="Ops Cost Diagnostics"
          action={<span className="label-muted">Hidden mode (`ops=1`)</span>}
        >
          <div className="space-y-5">
            <CostOpsFiltersBar
              showPresets={false}
              preset={opsPreset}
              startDate={opsStartDate}
              endDate={opsEndDate}
              exportUrl={opsExportUrl}
              loading={opsLoading}
              chartTableMode={opsViewMode}
              onChartTableModeChange={setOpsViewMode}
              onPresetChange={(preset) => {
                if (preset === "all") return
                applyOpsPreset(preset)
              }}
              onStartDateChange={(value) => {
                setOpsPreset("custom")
                setOpsStartDate(value)
              }}
              onEndDateChange={(value) => {
                setOpsPreset("custom")
                setOpsEndDate(value)
              }}
              onRefresh={() => { void opsAggregatesQuery.refetch() }}
            />

            {opsError && (
              <div className="rounded-lg border border-intent-danger-border bg-intent-danger-subtle px-4 py-3 text-sm text-intent-danger">
                {opsError}
              </div>
            )}

            {opsLoading && !opsAggregates && <CostsLoadingState />}

            {opsAggregates && (
              <>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <div className={cn(statCardClass, "min-w-0")}>
                    <div className="text-xs uppercase tracking-wide text-muted">Total cost</div>
                    <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                      {formatUsd(Number(opsAggregates.totals?.total_cost_usd || 0))}
                    </div>
                  </div>
                  <div className={cn(statCardClass, "min-w-0")}>
                    <div className="text-xs uppercase tracking-wide text-muted">Total calls</div>
                    <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                      {formatInteger(Number(opsAggregates.totals?.total_calls || 0))}
                    </div>
                  </div>
                  <div className={cn(statCardClass, "min-w-0")}>
                    <div className="text-xs uppercase tracking-wide text-muted">Input tokens</div>
                    <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                      {formatInteger(Number(opsAggregates.totals?.total_tokens_in || 0))}
                    </div>
                  </div>
                  <div className={cn(statCardClass, "min-w-0")}>
                    <div className="text-xs uppercase tracking-wide text-muted">Output tokens</div>
                    <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                      {formatInteger(Number(opsAggregates.totals?.total_tokens_out || 0))}
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <CostOpsSpendSection
                    byDay={opsAggregates.by_day}
                    byWeek={opsAggregates.by_week}
                    byMonth={opsAggregates.by_month}
                    viewMode={opsViewMode}
                  />
                  <div className={costOpsGridClass}>
                    <CostOpsPhaseSection title="Top phases" rows={opsAggregates.by_phase} viewMode={opsViewMode} />
                    <CostOpsGroupSection title="Top models" rows={opsAggregates.by_model} viewMode={opsViewMode} axisLabelKind="model" />
                  </div>
                </div>
              </>
            )}
          </div>
        </PageSection>
      )}

      {(screeningDiagnostics || validationSummary) && (
        <PageSection title="Validation and Screening Diagnostics">
          <div className="space-y-3 text-xs text-foreground">
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
        </PageSection>
      )}
    </div>
  )
}
