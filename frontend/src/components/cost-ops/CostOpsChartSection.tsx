import { useMemo, useState } from "react"
import { LoadingPane } from "@/components/ui/feedback"
import { CHART_THEME } from "@/lib/constants"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import type { DbCostAggregateBucketRow, DbCostAggregateGroupRow } from "@/lib/api"
import type { ChartTableMode } from "./ChartTableToggle"
import {
  costOpsSegmentButtonClass,
  costOpsSegmentGroupClass,
  costOpsSpendGranularityLabel,
  COST_OPS_SPEND_GRANULARITIES,
  formatAxisCost,
  formatCostGroupAxisLabel,
  formatInteger,
  formatPhaseName,
  formatSpendBucketAxisLabel,
  formatSpendBucketLabel,
  formatUsd,
  sectionHeaderClass,
  type CostOpsGroupAxisKind,
  type CostOpsSpendGranularity,
} from "./costOpsFormatters"

export function CostOpsRawTable({
  rows,
  labelHeader,
}: {
  rows: Array<{ label: string; calls: number; cost_usd: number }>
  labelHeader: string
}) {
  return (
    <div className="max-h-36 overflow-auto">
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
              <td className="px-2 py-1 max-w-[10rem] truncate" title={row.label}>{row.label}</td>
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
  axisLabelKind = "generic",
  maxBars = 8,
}: {
  title: string
  labelHeader: string
  rows: Array<{ label: string; calls: number; cost_usd: number }>
  viewMode: ChartTableMode
  axisLabelKind?: CostOpsGroupAxisKind
  maxBars?: number
}) {
  const chartData = rows.slice(0, maxBars).map((row) => ({
    label: row.label,
    axisLabel: formatCostGroupAxisLabel(row.label, axisLabelKind),
    calls: row.calls,
    cost_usd: Number(row.cost_usd.toFixed(6)),
  }))

  return (
    <div className="relative rounded-xl border border-border/80 bg-card/60">
      <div className={sectionHeaderClass}>
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="px-2.5 py-3 text-xs text-muted">No cost records in this window.</div>
      ) : viewMode === "table" ? (
        <CostOpsRawTable rows={rows} labelHeader={labelHeader} />
      ) : (
        <div className="h-40 px-1.5 pb-1 pt-0.5">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 4 }}>
              <XAxis
                dataKey="axisLabel"
                angle={-38}
                textAnchor="end"
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
                interval={0}
                height={42}
              />
              <YAxis
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
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

  const chartData = bucketRows.slice(-24).map((row) => ({
    bucket: row.bucket,
    label: row.label,
    axisLabel: row.axisLabel,
    calls: row.calls,
    cost_usd: Number(row.cost_usd.toFixed(6)),
  }))

  const denseAxis = chartData.length > 8

  return (
    <div className="relative rounded-xl border border-border/80 bg-card/60">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/80 px-2.5 py-1.5">
        <div className="text-xs font-semibold text-foreground">Spend over time</div>
        <div className={costOpsSegmentGroupClass}>
          {COST_OPS_SPEND_GRANULARITIES.map((key) => (
            <button
              key={key}
              type="button"
              className={costOpsSegmentButtonClass(granularity === key)}
              onClick={() => setGranularity(key)}
              aria-pressed={granularity === key}
            >
              {costOpsSpendGranularityLabel(key)}
            </button>
          ))}
        </div>
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
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
                interval={denseAxis ? "preserveStartEnd" : 0}
                height={denseAxis ? 36 : 18}
              />
              <YAxis
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
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
  axisLabelKind = "generic",
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
  viewMode: ChartTableMode
  formatLabels?: (key: string) => string
  axisLabelKind?: CostOpsGroupAxisKind
}) {
  const labelFormatter = formatLabels ?? ((key: string) => key)
  return (
    <CostOpsChartSection
      title={title}
      labelHeader="Group"
      viewMode={viewMode}
      axisLabelKind={axisLabelKind}
      rows={rows.slice(0, 12).map((row) => ({
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
  return (
    <CostOpsGroupSection
      title={title}
      rows={rows}
      viewMode={viewMode}
      formatLabels={formatPhaseName}
      axisLabelKind="phase"
    />
  )
}

export function CostsLoadingState() {
  return <LoadingPane message="Loading costs..." className="min-h-56" />
}
