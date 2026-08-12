import { Spinner } from "@/components/ui/feedback"
import { CHART_THEME } from "@/lib/constants"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import type { DbCostAggregateBucketRow, DbCostAggregateGroupRow } from "@/lib/api"
import { CostChartTooltip } from "./CostChartTooltip"
import type { ChartTableMode } from "./ChartTableToggle"
import {
  formatAxisCost,
  formatInteger,
  formatPhaseName,
  formatUsd,
  costOpsGridClass,
  sectionHeaderClass,
  statCardClass,
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
}: {
  title: string
  labelHeader: string
  rows: Array<{ label: string; calls: number; cost_usd: number }>
  viewMode: ChartTableMode
}) {
  const chartData = rows.slice(0, 12).map((row) => ({
    label: row.label,
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
        <div className="h-28 px-1.5 pb-2 pt-0.5">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <XAxis
                dataKey="label"
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
                tickFormatter={(value: string) => (value.length > 10 ? `${value.slice(0, 10)}...` : value)}
                interval="preserveStartEnd"
                height={16}
              />
              <YAxis
                tick={{ fill: CHART_THEME.tickFill, fontSize: 9 }}
                tickFormatter={formatAxisCost}
                width={52}
              />
              <Tooltip content={<CostChartTooltip />} cursor={{ fill: CHART_THEME.cursorFill }} />
              <Bar dataKey="cost_usd" fill={CHART_THEME.seriesPrimary} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export function CostOpsBucketSection({
  title,
  rows,
  viewMode,
}: {
  title: string
  rows: DbCostAggregateBucketRow[]
  viewMode: ChartTableMode
}) {
  return (
    <CostOpsChartSection
      title={title}
      labelHeader="Bucket"
      viewMode={viewMode}
      rows={rows.map((row) => ({
        label: row.bucket,
        calls: row.calls,
        cost_usd: row.cost_usd,
      }))}
    />
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
    />
  )
}

export function CostsLoadingSkeleton() {
  return (
    <div className="space-y-2">
      <div className="grid gap-2 grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={`stat-skeleton-${index}`}
            className={`${statCardClass} flex items-center justify-center`}
          >
            <div className="flex items-center gap-2 text-xs text-muted">
              <Spinner size="sm" />
              <span>Loading</span>
            </div>
          </div>
        ))}
      </div>

      <div className={costOpsGridClass}>
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={`chart-skeleton-${index}`}
            className="rounded-lg border border-border/80 bg-card/60"
          >
            <div className="border-b border-border/80 px-2.5 py-1.5 text-xs font-semibold text-foreground">
              Loading
            </div>
            <div className="flex h-28 items-center justify-center">
              <Spinner size="sm" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
