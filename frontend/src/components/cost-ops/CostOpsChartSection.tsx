import { useMemo, useState } from "react"
import { LoadingPane } from "@/components/ui/feedback"
import { CHART_THEME, phaseTitle } from "@/lib/constants"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import type { DbCostAggregateBucketRow, DbCostAggregateGroupRow } from "@/lib/api"
import { cn } from "@/lib/utils"
import { SegmentedControl, type ChartTableMode, type SegmentOption } from "./ChartTableToggle"
import {
  bucketOther,
  describeModelGroup,
  lastN,
  mergePhaseAliases,
  sortByCostDesc,
  type CostGroupLabel,
  wrapLabel,
  type CostRow,
} from "./costBreakdown"
import {
  costOpsSpendGranularityLabel,
  COST_OPS_SPEND_GRANULARITIES,
  formatAxisCost,
  formatInteger,
  formatPhaseName,
  formatSpendBucketAxisLabel,
  formatSpendBucketLabel,
  formatUsd,
  niceCostTicks,
  usdFormatterFor,
  sectionHeaderClass,
  type CostOpsSpendGranularity,
} from "./costOpsFormatters"

const SPEND_MAX_BUCKETS = 24
const SPEND_MAX_BAR_PX = 48
const CATEGORY_AXIS_WIDTH = 176
/** ~6px per character at 11px Inter, minus the 6px gap to the bar. */
const CATEGORY_LABEL_CHARS = Math.floor((CATEGORY_AXIS_WIDTH - 10) / 6)
const LABEL_LINE_HEIGHT = 13
const SUBLABEL_LINE_HEIGHT = 12

interface CategoryTickProps {
  x?: number
  y?: number
  payload?: { value?: string }
  rowsByKey: Map<string, CostRow>
}

function CategoryTick({ x = 0, y = 0, payload, rowsByKey }: CategoryTickProps) {
  const key = String(payload?.value ?? "")
  const row = rowsByKey.get(key)
  const label = row?.label ?? key
  const sublabel = row?.sublabel
  const lines = wrapLabel(label, CATEGORY_LABEL_CHARS)
  const blockHeight = lines.length * LABEL_LINE_HEIGHT + (sublabel ? SUBLABEL_LINE_HEIGHT : 0)
  const firstBaseline = -blockHeight / 2 + LABEL_LINE_HEIGHT - 3
  return (
    <g transform={`translate(${x},${y})`}>
      <title>{row?.title ?? label}</title>
      <text x={-6} y={firstBaseline} textAnchor="end" fill={CHART_THEME.tickFill} fontSize={11}>
        {lines.map((line, i) => (
          <tspan key={i} x={-6} dy={i === 0 ? 0 : LABEL_LINE_HEIGHT}>
            {line}
          </tspan>
        ))}
      </text>
      {sublabel && (
        <text
          x={-6}
          y={firstBaseline + lines.length * LABEL_LINE_HEIGHT - 1}
          textAnchor="end"
          fill={CHART_THEME.tickFill}
          fillOpacity={0.7}
          fontSize={10}
        >
          {wrapLabel(sublabel, CATEGORY_LABEL_CHARS, 1)[0]}
        </text>
      )}
    </g>
  )
}

function categoryRowHeight(rows: readonly CostRow[]): number {
  const tallest = Math.max(
    0,
    ...rows.map(
      (row) =>
        wrapLabel(row.label, CATEGORY_LABEL_CHARS).length * LABEL_LINE_HEIGHT
        + (row.sublabel ? SUBLABEL_LINE_HEIGHT : 0),
    ),
  )
  return Math.max(28, tallest + 8)
}

function rowKey(row: CostRow): string {
  return row.key ?? row.label
}

const GRANULARITY_OPTIONS: readonly SegmentOption<CostOpsSpendGranularity>[] =
  COST_OPS_SPEND_GRANULARITIES.map((value) => ({ value, label: costOpsSpendGranularityLabel(value) }))

export function CostOpsRawTable({
  rows,
  labelHeader,
}: {
  rows: CostRow[]
  labelHeader: string
}) {
  const fmtUsd = usdFormatterFor(rows.map((row) => row.cost_usd))
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
            <tr key={`${labelHeader}-${rowKey(row)}`} className="border-t border-border text-foreground">
              <td className="px-2 py-1 max-w-[16rem]" title={row.title ?? row.label}>
                <div className="line-clamp-2 [overflow-wrap:anywhere]">{row.label}</div>
                {row.sublabel && <div className="truncate text-2xs text-muted">{row.sublabel}</div>}
              </td>
              <td className="num px-2 py-1 text-right">{formatInteger(row.calls)}</td>
              <td className="num px-2 py-1 text-right">{fmtUsd(row.cost_usd)}</td>
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
  className,
}: {
  title: string
  labelHeader: string
  rows: CostRow[]
  viewMode: ChartTableMode
  maxBars?: number
  className?: string
}) {
  const sorted = useMemo(() => sortByCostDesc(rows), [rows])
  const { rows: bucketed, otherCount } = useMemo(() => bucketOther(sorted, maxBars), [sorted, maxBars])
  const chartData = bucketed.map((row) => ({
    key: rowKey(row),
    label: row.label,
    calls: row.calls,
    cost_usd: Number(row.cost_usd.toFixed(6)),
  }))
  const rowsByKey = useMemo(() => new Map(bucketed.map((row) => [rowKey(row), row])), [bucketed])
  const rowHeight = categoryRowHeight(bucketed)
  const fmtUsd = usdFormatterFor(bucketed.map((row) => row.cost_usd))

  return (
    <div className={cn("relative min-w-0 rounded-panel border border-border/80 bg-card/60", className)}>
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
        <div className="px-1.5 pb-3 pt-1" style={{ height: chartData.length * rowHeight + 24 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              layout="vertical"
              margin={{ top: 2, right: 64, left: 0, bottom: 2 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="key"
                width={CATEGORY_AXIS_WIDTH}
                tick={<CategoryTick rowsByKey={rowsByKey} />}
                axisLine={false}
                tickLine={false}
                interval={0}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const row = payload[0]?.payload as { key?: string; label?: string; cost_usd?: number; calls?: number }
                  const source = row.key ? rowsByKey.get(row.key) : undefined
                  return (
                    <div className="max-w-xs rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
                      <div className="text-muted mb-1">{source?.title ?? row.label}</div>
                      <div className="num font-semibold text-foreground">
                        {fmtUsd(Number(row.cost_usd ?? 0))}
                      </div>
                      <div className="num text-muted">{formatInteger(Number(row.calls ?? 0))} calls</div>
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
                  formatter: (v: unknown) => fmtUsd(Number(v)),
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
  const yTicks = niceCostTicks(Math.max(0, ...chartData.map((row) => row.cost_usd)))

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
        <div className="h-36 px-1.5 pb-2 pt-3">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 4, left: 0, bottom: denseAxis ? 8 : 0 }}>
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
                ticks={yTicks}
                domain={[0, yTicks[yTicks.length - 1] || "auto"]}
                interval={0}
                width={52}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const row = payload[0]?.payload as { label?: string; cost_usd?: number }
                  return (
                    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-xl">
                      <div className="text-muted mb-1">{row.label}</div>
                      <div className="num font-semibold text-foreground">
                        {formatUsd(Number(row.cost_usd ?? 0))}
                      </div>
                    </div>
                  )
                }}
                cursor={{ fill: CHART_THEME.cursorFill }}
              />
              <Bar
                dataKey="cost_usd"
                fill={CHART_THEME.seriesPrimary}
                radius={[4, 4, 0, 0]}
                maxBarSize={SPEND_MAX_BAR_PX}
              />
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
  describeGroup,
  labelHeader = "Group",
  className,
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
  viewMode: ChartTableMode
  formatLabels?: (key: string) => string
  describeGroup?: (key: string) => CostGroupLabel
  labelHeader?: string
  className?: string
}) {
  const describe = describeGroup ?? ((key: string) => ({ label: formatLabels ? formatLabels(key) : key }))
  return (
    <CostOpsChartSection
      className={className}
      title={title}
      labelHeader={labelHeader}
      viewMode={viewMode}
      rows={rows.map((row) => ({
        key: row.group_key,
        ...describe(row.group_key),
        calls: row.calls,
        cost_usd: row.cost_usd,
      }))}
    />
  )
}

export function CostOpsModelSection({
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
      describeGroup={describeModelGroup}
      labelHeader="Model"
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
      describeGroup={(key) => ({ label: formatPhaseName(key), title: phaseTitle(key) })}
    />
  )
}

export function CostsLoadingState() {
  return <LoadingPane message="Loading costs..." className="min-h-56" />
}
