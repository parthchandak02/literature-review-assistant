import { useMemo, useState, type CSSProperties, type ReactNode } from "react"
import { Activity, ArrowUpDown, BarChart3, DollarSign, Download, Zap } from "lucide-react"
import { cn } from "@/lib/utils"
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
  CostOpsModelSection,
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
  usdFormatterFor,
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

interface PhaseBarRow {
  phase: string
  label: string
  title?: string
  cost_usd: number
  barLabel: string
}

/** Label beside the bar from sm up; stacked above it on phones so bars keep the full width. */
function PhaseCostBars({ rows }: { rows: PhaseBarRow[] }) {
  const max = Math.max(0, ...rows.map((r) => r.cost_usd))
  return (
    <ul className="flex flex-col gap-2 sm:gap-1.5" aria-label="Cost by phase">
      {rows.map((row, i) => {
        const pct = max > 0 ? Math.max(0.5, (row.cost_usd / max) * 100) : 0
        return (
          <li
            key={row.phase}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 text-xs sm:grid-cols-[10.5rem_minmax(0,1fr)]"
          >
            <span className="truncate text-muted sm:text-right" title={row.title ?? row.phase}>
              {row.label}
            </span>
            <span className="tabular-nums text-foreground sm:hidden">{row.barLabel}</span>
            <span className="col-span-2 flex min-w-0 items-center gap-2 sm:col-span-1">
              <span
                aria-hidden
                className={cn(
                  "h-2.5 shrink-0 rounded-r sm:h-4 w-[calc(100%*var(--bar))] sm:w-[calc((100%-7.5rem)*var(--bar))]",
                  i === 0 ? "bg-chart-series" : "bg-chart-series/45",
                )}
                style={{ "--bar": pct / 100 } as CSSProperties}
              />
              <span className="hidden shrink-0 tabular-nums text-foreground sm:inline">{row.barLabel}</span>
            </span>
          </li>
        )
      })}
    </ul>
  )
}

const thClass = "px-4 py-2.5 label-caps"
const numCellClass = "px-4 py-3 text-right tabular-nums text-xs"

function unitCostLines(totalCost: number, included: number | null | undefined, screened: number | null | undefined) {
  const perStudy = costPerUnit(totalCost, included)
  const perThousand = costPerUnit(totalCost, screened, 1000)
  const parts: { key: string; node: ReactNode }[] = []
  if (perStudy != null) {
    parts.push({
      key: "study",
      node: `${formatUsd(perStudy)} / included study`,
    })
  }
  if (perThousand != null) parts.push({ key: "screened", node: `${formatUsd(perThousand)} / 1k screened` })
  if (parts.length === 0) return undefined
  return parts.map(({ key, node }) => (
    <span key={key} className="block" data-testid={`cost-unit-${key}`}>
      {node}
    </span>
  ))
}

interface CostViewProps {
  costStats: CostStats
  dbRunId?: string | null
  isLive?: boolean
  isSSEConnected?: boolean
  /** Final included-study count for per-study cost. */
  includedCount?: number | null
  /** Records that reached reviewer screening (PRISMA "records screened") for per-1k-screened cost. */
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
  const fmtPhaseUsd = usdFormatterFor([...phaseRows.map((r) => r.cost_usd), phaseTotals.cost])
  const fmtModelUsd = usdFormatterFor(by_model.map((m) => m.cost_usd))
  const chartData = phaseRows.map((r) => ({
    ...r,
    barLabel: `${fmtPhaseUsd(r.cost_usd)} · ${formatShare(r.share)}`,
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
          <Button variant="outline" size="xs" asChild>
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
          sub={unitCostLines(total_cost, includedCount, screenedCount)}
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
          value={formatCompact(total_tokens_in)}
          valueTitle={`${formatInteger(total_tokens_in)} tokens`}
        />
        <StatTile
          icon={ArrowUpDown}
          label="Tokens out"
          value={formatCompact(total_tokens_out)}
          valueTitle={`${formatInteger(total_tokens_out)} tokens`}
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
              <PhaseCostBars rows={chartData} />
            ) : (
              <p className="label-muted text-center py-4">
                Cost breakdown will appear as phases complete.
              </p>
            )
          ) : (
            <div className="bg-card overflow-x-auto">
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
                      <td className="px-5 py-3 text-foreground text-xs" title={p.title ?? p.phase}>{p.label}</td>
                      <td className={cn(numCellClass, "text-muted")}>{formatInteger(p.calls)}</td>
                      <td className={cn(numCellClass, "font-medium text-foreground")}>{fmtPhaseUsd(p.cost_usd)}</td>
                      <td className={cn(numCellClass, "px-5 text-muted")}>{formatShare(p.share)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border/70">
                    <td className="px-5 py-3 text-xs font-semibold text-foreground">Total</td>
                    <td className={cn(numCellClass, "font-semibold text-foreground")}>{formatInteger(phaseTotals.calls)}</td>
                    <td className={cn(numCellClass, "font-semibold text-foreground")}>{fmtPhaseUsd(phaseTotals.cost)}</td>
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
          <div className="bg-card overflow-x-auto">
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
                      <td className={cn(numCellClass, "text-muted")} title={formatInteger(m.tokens_in)}>{formatCompact(m.tokens_in)}</td>
                      <td className={cn(numCellClass, "text-muted")} title={formatInteger(m.tokens_out)}>{formatCompact(m.tokens_out)}</td>
                      <td className={cn(numCellClass, "font-medium text-foreground")}>{fmtModelUsd(m.cost_usd)}</td>
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
                  <StatTile
                    label="Input tokens"
                    value={formatCompact(Number(opsAggregates.totals?.total_tokens_in || 0))}
                    valueTitle={`${formatInteger(Number(opsAggregates.totals?.total_tokens_in || 0))} tokens`}
                  />
                  <StatTile
                    label="Output tokens"
                    value={formatCompact(Number(opsAggregates.totals?.total_tokens_out || 0))}
                    valueTitle={`${formatInteger(Number(opsAggregates.totals?.total_tokens_out || 0))} tokens`}
                  />
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
                    <CostOpsModelSection title="Top models" rows={opsAggregates.by_model} viewMode={opsViewMode} />
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
