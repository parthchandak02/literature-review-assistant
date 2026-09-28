import { useMemo, useState } from "react"
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, LabelList } from "recharts"
import { Activity, ArrowUpDown, BarChart3, DollarSign, Download, Zap } from "lucide-react"
import { cn } from "@/lib/utils"
import { CHART_THEME } from "@/lib/constants"
import { getDbCostExportUrl } from "@/lib/api"
import { shortModelName } from "@/lib/humanize"
import { buildCostStatsFromDashboard, type CostStats } from "@/hooks/useCostStats"
import {
  costsFetchErrorMessage,
  useDbCostAggregates,
  useDbCostDashboard,
} from "@/hooks/useDbCosts"
import { Button } from "@/components/ui/button"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { SkeletonCard } from "@/components/ui/skeleton"
import { PageSection } from "@/components/ui/section"
import { StatTile } from "@/components/ui/stat-tile"
import { ChartTableToggle, type ChartTableMode } from "@/components/cost-ops/ChartTableToggle"
import { CostOpsFiltersBar } from "@/components/cost-ops/CostOpsFiltersBar"
import {
  CostOpsGroupSection,
  CostOpsPhaseSection,
  CostOpsSpendSection,
  CostsLoadingState,
} from "@/components/cost-ops/CostOpsChartSection"
import {
  buildPresetRange,
  costOpsPairGridClass,
  formatInteger,
  formatUsd,
  toApiEnd,
  toApiStart,
} from "@/components/cost-ops/costOpsFormatters"
import {
  buildPhaseCostRows,
  costEmptyHeading,
  costPerUnit,
  formatCompact,
  formatShare,
  withShare,
  type CostRunState,
} from "@/components/cost-ops/costBreakdown"

const PHASE_BAR_HEIGHT = 32
const MUTED_BAR_OPACITY = 0.45

const thClass = "px-4 py-2.5 label-caps"
const numCellClass = "px-4 py-3 text-right tabular-nums text-xs"

function unitCostLine(totalCost: number, included: number | null | undefined, screened: number | null | undefined) {
  const perStudy = costPerUnit(totalCost, included)
  const perThousand = costPerUnit(totalCost, screened, 1000)
  const parts = [
    perStudy != null ? `${formatUsd(perStudy)} / included study` : null,
    perThousand != null ? `${formatUsd(perThousand)} / 1k screened` : null,
  ].filter(Boolean)
  return parts.length > 0 ? parts.join(" · ") : undefined
}

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  isLive?: boolean
  isSSEConnected?: boolean
  /** Final included-study count for per-study cost. */
  includedCount?: number | null
  /** Records entering screening for per-1k-screened cost. */
  screenedCount?: number | null
  runState?: CostRunState
}

export function CostView({
  costStats,
  dbRunId,
  isLive,
  isSSEConnected,
  includedCount,
  screenedCount,
  runState = "not_started",
}: CostViewProps) {
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

  const loadingDb = dashboardQuery.isLoading
  const dbError = dashboardQuery.isError ? costsFetchErrorMessage(dashboardQuery.error) : null
  const opsAggregates = opsAggregatesQuery.data ?? null
  const opsLoading = opsAggregatesQuery.isFetching
  const opsError = opsAggregatesQuery.isError
    ? opsAggregatesQuery.error instanceof Error
      ? opsAggregatesQuery.error.message
      : String(opsAggregatesQuery.error)
    : null

  // DB data is the primary source; SSE-derived stats are a fallback before the first poll.
  const activeCostStats = dbCostStats ?? costStats
  const { total_cost, total_tokens_in, total_tokens_out, total_calls, by_model, by_phase } = activeCostStats

  const phaseRows = useMemo(() => buildPhaseCostRows(by_phase), [by_phase])
  const phaseTotals = useMemo(
    () => phaseRows.reduce((acc, r) => ({ calls: acc.calls + r.calls, cost: acc.cost + r.cost_usd }), { calls: 0, cost: 0 }),
    [phaseRows],
  )
  const modelRows = useMemo(() => withShare(by_model), [by_model])
  const chartData = phaseRows.map((r) => ({
    ...r,
    barLabel: `${formatUsd(r.cost_usd)} · ${formatShare(r.share)}`,
  }))
  const nonZeroPhasesCount = phaseRows.filter((d) => d.cost_usd > 0).length

  const hasCosts = total_calls > 0 || total_cost > 0
  const runExportUrl = dbRunId ? getDbCostExportUrl(dbRunId, { granularity: "day" }) : ""
  const opsExportUrl = dbRunId
    ? getDbCostExportUrl(dbRunId, {
      start_ts: toApiStart(opsStartDate),
      end_ts: toApiEnd(opsEndDate),
      granularity: "day",
    })
    : ""

  if (loadingDb) {
    return (
      <div className="flex flex-col gap-4">
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
    return <EmptyState icon={DollarSign} heading={costEmptyHeading(runState)} className="h-64" />
  }

  const perCall = costPerUnit(total_cost, total_calls)

  return (
    <div className="flex flex-col gap-6 min-w-0">
      {dbRunId && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" asChild>
            <a href={runExportUrl} download>
              <Download aria-hidden />
              Export CSV
            </a>
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          icon={DollarSign}
          label="Total cost"
          value={formatUsd(total_cost)}
          sub={unitCostLine(total_cost, includedCount, screenedCount)}
        />
        <StatTile
          icon={Activity}
          label="LLM calls"
          value={formatInteger(total_calls)}
          sub={perCall != null ? `${formatUsd(perCall)} / call` : undefined}
        />
        <StatTile
          icon={Zap}
          label="Tokens in"
          value={`${formatCompact(total_tokens_in)} tokens`}
        />
        <StatTile
          icon={ArrowUpDown}
          label="Tokens out"
          value={`${formatCompact(total_tokens_out)} tokens`}
        />
      </div>

      {phaseRows.length > 0 && (
        <PageSection
          icon={BarChart3}
          title="Cost by phase"
          action={
            <ChartTableToggle
              mode={phaseViewMode}
              onChange={setPhaseViewMode}
              ariaLabel="Cost by phase display"
            />
          }
          contentClassName={phaseViewMode === "table" ? "p-0" : undefined}
        >
          {phaseViewMode === "chart" ? (
            nonZeroPhasesCount >= 2 ? (
              <ResponsiveContainer width="100%" height={chartData.length * PHASE_BAR_HEIGHT + 8}>
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ left: 4, right: 112, top: 4, bottom: 4 }}
                >
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="label"
                    width={168}
                    tick={{ fill: CHART_THEME.tickFill, fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <Bar dataKey="cost_usd" radius={[0, 4, 4, 0]} barSize={18} isAnimationActive={false}>
                    {chartData.map((entry, i) => (
                      <Cell
                        key={entry.phase}
                        fill={CHART_THEME.seriesPrimary}
                        fillOpacity={i === 0 ? 1 : MUTED_BAR_OPACITY}
                      />
                    ))}
                    <LabelList
                      dataKey="barLabel"
                      position="right"
                      fill="var(--color-foreground)"
                      fontSize={12}
                    />
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
                    <th className={cn(thClass, "text-left px-5")}>Phase</th>
                    <th className={cn(thClass, "text-right")}>Calls</th>
                    <th className={cn(thClass, "text-right")}>Cost</th>
                    <th className={cn(thClass, "text-right px-5")}>Share</th>
                  </tr>
                </thead>
                <tbody>
                  {phaseRows.map((p) => (
                    <tr key={p.phase} className="border-b border-border/50 hover:bg-surface-2/40 transition-colors">
                      <td className="px-5 py-3 text-foreground text-xs" title={p.phase}>{p.label}</td>
                      <td className={cn(numCellClass, "text-muted")}>{formatInteger(p.calls)}</td>
                      <td className={cn(numCellClass, "font-medium text-foreground")}>{formatUsd(p.cost_usd)}</td>
                      <td className={cn(numCellClass, "px-5 text-muted")}>{formatShare(p.share)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border/70">
                    <td className="px-5 py-3 text-xs font-semibold text-foreground">Total</td>
                    <td className={cn(numCellClass, "font-semibold text-foreground")}>{formatInteger(phaseTotals.calls)}</td>
                    <td className={cn(numCellClass, "font-semibold text-foreground")}>{formatUsd(phaseTotals.cost)}</td>
                    <td className={cn(numCellClass, "px-5 font-semibold text-foreground")}>100%</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </PageSection>
      )}

      {modelRows.length > 0 && (
        <PageSection title="Cost by model" contentClassName="p-0">
          <div className="data-surface overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="glass-table-head border-b border-border/70">
                  <th className={cn(thClass, "text-left px-5")}>Model</th>
                  <th className={cn(thClass, "text-right")}>Calls</th>
                  <th className={cn(thClass, "text-right")}>Tokens in</th>
                  <th className={cn(thClass, "text-right")}>Tokens out</th>
                  <th className={cn(thClass, "text-right")}>Cost</th>
                  <th className={cn(thClass, "text-right px-5")}>Share</th>
                </tr>
              </thead>
              <tbody>
                {modelRows.map(({ row: m, share }, i) => {
                  const { name, provider } = shortModelName(m.model)
                  return (
                    <tr
                      key={m.model}
                      className={cn(
                        "border-b border-border/50 hover:bg-surface-2/40 transition-colors",
                        i === modelRows.length - 1 && "border-0",
                      )}
                    >
                      <td className="px-5 py-3 text-xs" title={m.model}>
                        <span className="font-mono text-foreground">{name || m.model}</span>
                        {provider && <span className="ml-2 text-muted">{provider}</span>}
                      </td>
                      <td className={cn(numCellClass, "text-muted")}>{formatInteger(m.calls)}</td>
                      <td className={cn(numCellClass, "text-muted")}>{formatCompact(m.tokens_in)}</td>
                      <td className={cn(numCellClass, "text-muted")}>{formatCompact(m.tokens_out)}</td>
                      <td className={cn(numCellClass, "font-medium text-foreground")}>{formatUsd(m.cost_usd)}</td>
                      <td className={cn(numCellClass, "px-5 text-muted")}>{formatShare(share)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </PageSection>
      )}

      {opsEnabled && dbRunId && (
        <PageSection title="Ops cost diagnostics">
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
                  <StatTile label="Total cost" value={formatUsd(Number(opsAggregates.totals?.total_cost_usd || 0))} />
                  <StatTile label="Total calls" value={formatInteger(Number(opsAggregates.totals?.total_calls || 0))} />
                  <StatTile label="Input tokens" value={formatCompact(Number(opsAggregates.totals?.total_tokens_in || 0))} />
                  <StatTile label="Output tokens" value={formatCompact(Number(opsAggregates.totals?.total_tokens_out || 0))} />
                </div>

                <div className="space-y-2">
                  <CostOpsSpendSection
                    byDay={opsAggregates.by_day}
                    byWeek={opsAggregates.by_week}
                    byMonth={opsAggregates.by_month}
                    viewMode={opsViewMode}
                  />
                  <div className={costOpsPairGridClass}>
                    <CostOpsPhaseSection title="Top phases" rows={opsAggregates.by_phase} viewMode={opsViewMode} />
                    <CostOpsGroupSection title="Top models" rows={opsAggregates.by_model} viewMode={opsViewMode} />
                  </div>
                </div>
              </>
            )}
          </div>
        </PageSection>
      )}
    </div>
  )
}
