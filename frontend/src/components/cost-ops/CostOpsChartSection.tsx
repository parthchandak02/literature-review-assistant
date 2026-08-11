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
    <div className="max-h-56 overflow-auto">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-card/95 text-muted">
          <tr>
            <th className="px-4 py-2 text-left font-medium">{labelHeader}</th>
            <th className="px-4 py-2 text-right font-medium">Calls</th>
            <th className="px-4 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${labelHeader}-${row.label}`} className="border-t border-border text-foreground">
              <td className="px-4 py-2">{row.label}</td>
              <td className="px-4 py-2 text-right">{formatInteger(row.calls)}</td>
              <td className="px-4 py-2 text-right">{formatUsd(row.cost_usd)}</td>
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
        <div className="px-4 py-6 text-sm text-muted">No cost records in this window.</div>
      ) : viewMode === "table" ? (
        <CostOpsRawTable rows={rows} labelHeader={labelHeader} />
      ) : (
        <div className="h-48 px-2 pb-3 pt-1">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 12, right: 8, left: 0, bottom: 4 }}>
              <XAxis
                dataKey="label"
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                tickFormatter={(value: string) => (value.length > 12 ? `${value.slice(0, 12)}...` : value)}
                interval="preserveStartEnd"
                height={20}
              />
              <YAxis
                tick={{ fill: CHART_THEME.tickFill, fontSize: 11 }}
                tickFormatter={formatAxisCost}
                width={70}
              />
              <Tooltip content={<CostChartTooltip />} cursor={{ fill: CHART_THEME.cursorFill }} />
              <Bar dataKey="cost_usd" fill={CHART_THEME.seriesPrimary} radius={[6, 6, 0, 0]} />
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
    <div className="space-y-4">
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={`stat-skeleton-${index}`}
            className={`${statCardClass} flex items-center justify-center`}
          >
            <div className="flex items-center gap-2 text-sm text-muted">
              <Spinner size="sm" />
              <span>Loading metric</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={`bucket-skeleton-${index}`}
            className="rounded-xl border border-border/80 bg-card/60 p-4"
          >
            <div className="text-sm font-semibold text-foreground">
              Loading chart
            </div>
            <div className="flex h-40 items-center justify-center">
              <Spinner size="lg" />
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={`group-skeleton-${index}`}
            className="rounded-xl border border-border/80 bg-card/60 p-4"
          >
            <div className="text-sm font-semibold text-foreground">
              Loading breakdown
            </div>
            <div className="flex h-40 items-center justify-center">
              <Spinner size="lg" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
