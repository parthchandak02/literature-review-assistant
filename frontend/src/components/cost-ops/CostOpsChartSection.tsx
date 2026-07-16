import { useState } from "react"
import { Table2 } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { CHART_THEME } from "@/lib/constants"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { Button } from "@/components/ui/button"
import type { DbCostAggregateBucketRow, DbCostAggregateGroupRow } from "@/lib/api"
import {
  formatAxisCost,
  formatInteger,
  formatUsd,
  sectionHeaderClass,
  statCardClass,
} from "./costOpsFormatters"

export function CostTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: Array<{ value?: number }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const value = Number(payload[0].value ?? 0)
  return (
    <div className="rounded-md border border-border bg-surface-2/95 px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-muted">{label}</div>
      <div className="font-medium text-foreground">{formatUsd(value)}</div>
    </div>
  )
}

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
}: {
  title: string
  labelHeader: string
  rows: Array<{ label: string; calls: number; cost_usd: number }>
}) {
  const [showRaw, setShowRaw] = useState(false)
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
      ) : showRaw ? (
        <>
          <CostOpsRawTable rows={rows} labelHeader={labelHeader} />
          <div className="border-t border-border/60 px-3 py-2">
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="h-8 rounded-lg border border-border bg-surface-2/70 px-3 text-foreground hover:bg-surface-3"
                onClick={() => setShowRaw(false)}
              >
                Show chart
              </Button>
            </div>
          </div>
        </>
      ) : (
        <div className="h-48 px-2 pb-1 pt-1">
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
              <Tooltip content={<CostTooltip />} />
              <Bar dataKey="cost_usd" fill={CHART_THEME.seriesPrimary} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {!showRaw && rows.length > 0 && (
        <div className="border-t border-border/60 px-3 py-2">
          <div className="flex justify-end">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-8 rounded-lg border border-border bg-surface-2/85 px-2.5 text-foreground hover:bg-surface-3"
              onClick={() => setShowRaw(true)}
              title="Show raw table"
            >
              <Table2 className="h-3.5 w-3.5" />
              Raw table
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export function CostOpsBucketSection({
  title,
  rows,
}: {
  title: string
  rows: DbCostAggregateBucketRow[]
}) {
  return (
    <CostOpsChartSection
      title={title}
      labelHeader="Bucket"
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
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
}) {
  return (
    <CostOpsChartSection
      title={title}
      labelHeader="Group"
      rows={rows.slice(0, 12).map((row) => ({
        label: row.group_key,
        calls: row.calls,
        cost_usd: row.cost_usd,
      }))}
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
