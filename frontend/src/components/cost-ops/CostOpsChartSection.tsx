import { useMemo, useState } from "react"
import { LoadingPane } from "@/components/ui/feedback"
import { CHART_THEME } from "@/lib/constants"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import type { DbCostAggregateBucketRow, DbCostAggregateGroupRow } from "@/lib/api"
import { cn } from "@/lib/utils"
import { SegmentedControl, type ChartTableMode, type SegmentOption } from "./ChartTableToggle"
import { bucketOther, lastN, mergePhaseAliases, sortByCostDesc, type CostRow } from "./costBreakdown"
import {
  costOpsSpendGranularityLabel,
  COST_OPS_SPEND_GRANULARITIES,
  formatAxisCost,
  formatInteger,
  formatPhaseName,
  formatSpendBucketAxisLabel,
  formatSpendBucketLabel,
  formatUsd,
  sectionHeaderClass,
  type CostOpsSpendGranularity,
} from "./costOpsFormatters"

const SPEND_MAX_BUCKETS = 24

const GRANULARITY_OPTIONS: readonly SegmentOption<CostOpsSpendGranularity>[] =
  COST_OPS_SPEND_GRANULARITIES.map((value) => ({ value, label: costOpsSpendGranularityLabel(value) }))

export function CostOpsRawTable({
  rows,
  labelHeader,
}: {
  rows: CostRow[]
  labelHeader: string
}) {
  return (
    <div className="max-h-72 overflow-auto">
      <table className="min-w-full text-xs">
        <thead className="sticky top-0 bg-card/95 text-muted">
          <tr>
            <th className="px-2 py-1 text-left font-medium">{labelHeader}</th>
            <th className="px-2 py-1 text-right font-medium">Calls</th>
            <th className="px-2 py-1 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${labelHeader}-${row.label}`} className="border-t border-border text-foreground">
              <td className="px-2 py-1 max-w-[16rem] truncate" title={row.label}>{row.label}</td>
              <td className="px-2 py-1 text-right tabular-nums">{formatInteger(row.calls)}</td>
              <td className="px-2 py-1 text-right tabular-nums">{formatUsd(row.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CostOpsChartSection({
  title,
  labelHeader,
  rows,
  viewMode,
  maxBars = 8,
}: {
  title: string
  labelHeader: string
  rows: CostRow[]
  viewMode: ChartTableMode
  maxBars?: number
}) {
  const sorted = useMemo(() => sortByCostDesc(rows), [rows])
  const { rows: bucketed, otherCount } = useMemo(() => bucketOther(sorted, maxBars), [sorted, maxBars])
  const chartData = bucketed.map((row) => ({
    label: row.label,
    calls: row.calls,
    cost_usd: Number(row.cost_usd.toFixed(6)),
  }))

  return (
    <div className="relative min-w-0 rounded-panel border border-border/80 bg-card/60">
      <div className={cn(sectionHeaderClass, "flex items-center justify-between gap-2")}>
        <span>{title}</span>
        {otherCount > 0 && viewMode === "chart" && (
          <span className="font-normal text-muted">
            Top {bucketed.length - 1} of {sorted.length}
          </span>
        )}
      </div>
      {rows.length === 0 ? (
        <div className="px-2.5 py-3 text-xs text-muted">No cost records in this window.</div>
      ) : viewMode === "table" ? (
        <CostOpsRawTable rows={sorted} labelHeader={labelHeader} />
      ) : (
        <div className="px-1.5 pb-1 pt-1" style={{ height: chartData.length * 28 + 12 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 2, right: 64, left: 0, bottom: 2 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="label"
                width={148}
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                interval={0}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const row = payload[0]?.payload as { label?: string; cost_usd?: number; calls?: number }
                  return (
                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
                      <div className="text-muted mb-1">{row.label}</div>
                      <div className="text-foreground font-mono font-semibold">
                        {formatUsd(Number(row.cost_usd ?? 0))}
                      </div>
                      <div className="text-muted tabular-nums">{formatInteger(Number(row.calls ?? 0))} calls</div>
                    </div>
                  )
                }}
                cursor={{ fill: CHART_THEME.cursorFill }}
              />
              <Bar
                dataKey="cost_usd"
                fill={CHART_THEME.seriesPrimary}
                radius={[0, 4, 4, 0]}
                barSize={16}
                label={{
                  position: "right",
                  formatter: (v: unknown) => formatUsd(Number(v)),
                  fill: CHART_THEME.tickFill,
                  fontSize: 11,
                }}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export function CostOpsSpendSection({
  byDay,
  byWeek,
  byMonth,
  viewMode,
}: {
  byDay: DbCostAggregateBucketRow[]
  byWeek: DbCostAggregateBucketRow[]
  byMonth: DbCostAggregateBucketRow[]
  viewMode: ChartTableMode
}) {
  const [granularity, setGranularity] = useState<CostOpsSpendGranularity>("day")

  const bucketRows = useMemo(() => {
    const source = granularity === "day" ? byDay : granularity === "week" ? byWeek : byMonth
    return source.map((row) => ({
      bucket: row.bucket,
      label: formatSpendBucketLabel(row.bucket, granularity),
      axisLabel: formatSpendBucketAxisLabel(row.bucket, granularity),
      calls: row.calls,
      cost_usd: row.cost_usd,
    }))
  }, [byDay, byMonth, byWeek, granularity])

  const { rows: visibleBuckets, hidden: hiddenBuckets } = lastN(bucketRows, SPEND_MAX_BUCKETS)
  const chartData = visibleBuckets.map((row) => ({
    bucket: row.bucket,
    label: row.label,
    axisLabel: row.axisLabel,
    calls: row.calls,
    cost_usd: Number(row.cost_usd.toFixed(6)),
  }))

  const denseAxis = chartData.length > 8

  return (
    <div className="relative rounded-panel border border-border/80 bg-card/60">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/80 px-2.5 py-1.5">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-semibold text-foreground">Spend over time</span>
          {hiddenBuckets > 0 && viewMode === "chart" && (
            <span className="text-xs text-muted">
              Showing last {SPEND_MAX_BUCKETS} of {bucketRows.length}
            </span>
          )}
        </div>
        <SegmentedControl
          value={granularity}
          options={GRANULARITY_OPTIONS}
          onChange={setGranularity}
          ariaLabel="Spend granularity"
        />
      </div>
      {bucketRows.length === 0 ? (
        <div className="px-2.5 py-3 text-xs text-muted">No cost records in this window.</div>
      ) : viewMode === "table" ? (
        <CostOpsRawTable rows={bucketRows} labelHeader="Period" />
      ) : (
        <div className="h-32 px-1.5 pb-2 pt-0.5">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: denseAxis ? 8 : 0 }}>
              <XAxis
                dataKey="axisLabel"
                angle={denseAxis ? -32 : 0}
                textAnchor={denseAxis ? "end" : "middle"}
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                interval={denseAxis ? "preserveStartEnd" : 0}
                height={denseAxis ? 36 : 18}
              />
              <YAxis
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                tickFormatter={formatAxisCost}
                width={52}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const row = payload[0]?.payload as { label?: string; cost_usd?: number }
                  return (
                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
                      <div className="text-muted mb-1">{row.label}</div>
                      <div className="text-foreground font-mono font-semibold">
                        {formatUsd(Number(row.cost_usd ?? 0))}
                      </div>
                    </div>
                  )
                }}
                cursor={{ fill: CHART_THEME.cursorFill }}
              />
              <Bar dataKey="cost_usd" fill={CHART_THEME.seriesPrimary} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export function CostOpsGroupSection({
  title,
  rows,
  viewMode,
  formatLabels,
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
  viewMode: ChartTableMode
  formatLabels?: (key: string) => string
}) {
  const labelFormatter = formatLabels ?? ((key: string) => key)
  return (
    <CostOpsChartSection
      title={title}
      labelHeader="Group"
      viewMode={viewMode}
      rows={rows.map((row) => ({
        label: labelFormatter(row.group_key),
        calls: row.calls,
        cost_usd: row.cost_usd,
      }))}
    />
  )
}

export function CostOpsPhaseSection({
  title,
  rows,
  viewMode,
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
  viewMode: ChartTableMode
}) {
  const merged = mergePhaseAliases(rows.map((r) => ({ ...r, phase: r.group_key })))
    .map(({ phase, ...rest }) => ({ ...rest, group_key: phase }))
  return (
    <CostOpsGroupSection
      title={title}
      rows={merged}
      viewMode={viewMode}
      formatLabels={formatPhaseName}
    />
  )
}

export function CostsLoadingState() {
  return <LoadingPane message="Loading costs..." className="min-h-56" />
}
