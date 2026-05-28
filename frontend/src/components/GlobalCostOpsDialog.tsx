import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CalendarDays, Download, RefreshCw, Table2, X } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { CHART_THEME } from "@/lib/constants"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import {
  fetchHistoryCostAggregates,
  getHistoryCostExportUrl,
} from "@/lib/api"
import type {
  DbCostAggregateBucketRow,
  DbCostAggregateGroupRow,
  DbCostExportGranularity,
  HistoryCostAggregatesResponse,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type PresetKey = "5d" | "30d" | "90d" | "custom"

interface GlobalCostOpsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function toDateInputValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function buildPresetRange(days: number): { startDate: string; endDate: string } {
  const end = new Date()
  const start = new Date(end)
  start.setDate(end.getDate() - (days - 1))
  return {
    startDate: toDateInputValue(start),
    endDate: toDateInputValue(end),
  }
}

function toApiStart(date: string): string | undefined {
  return date ? `${date} 00:00:00` : undefined
}

function toApiEnd(date: string): string | undefined {
  return date ? `${date} 23:59:59` : undefined
}

function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 1 ? 2 : 4,
    maximumFractionDigits: 4,
  }).format(value)
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}

const fieldLabelClass = "space-y-1.5 text-sm"
const fieldControlClass =
  "h-10 w-full min-w-0 rounded-lg border border-border bg-card/90 px-3 text-sm text-foreground shadow-sm outline-none transition-colors hover:border-border focus:border-intent-primary"
const statCardClass = "rounded-xl border border-border/80 bg-card/60 px-4 py-4"
const loadingStages = [
  "Preparing filters",
  "Fetching cost aggregates",
  "Building summaries",
  "Rendering breakdowns",
] as const
const sectionHeaderClass = "border-b border-border/80 px-4 py-3 text-sm font-semibold text-foreground"

function formatAxisCost(value: number): string {
  return `$${value >= 1 ? value.toFixed(2) : value.toFixed(4)}`
}

function CostTooltip({
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

function RawTable({
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

function ChartOrTableSection({
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
          <RawTable rows={rows} labelHeader={labelHeader} />
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

function BucketSection({
  title,
  rows,
}: {
  title: string
  rows: DbCostAggregateBucketRow[]
}) {
  return (
    <ChartOrTableSection
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

function GroupSection({
  title,
  rows,
}: {
  title: string
  rows: DbCostAggregateGroupRow[]
}) {
  return (
    <ChartOrTableSection
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

function CostsLoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-4">
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

      <div className="grid gap-4 xl:grid-cols-3">
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

      <div className="grid gap-4 xl:grid-cols-3">
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

/**
 * Standalone costs content panel -- can be rendered inside any container
 * (the SettingsDialog embeds it in its "Costs" tab).
 */
export function CostsPanel() {
  const defaultRange = useMemo(() => buildPresetRange(30), [])
  const [preset, setPreset] = useState<PresetKey>("30d")
  const [startDate, setStartDate] = useState(defaultRange.startDate)
  const [endDate, setEndDate] = useState(defaultRange.endDate)
  const [exportGranularity, setExportGranularity] = useState<DbCostExportGranularity>("day")
  const [loading, setLoading] = useState(false)
  const [loadingStageIndex, setLoadingStageIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<HistoryCostAggregatesResponse | null>(null)
  const activeRequestRef = useRef(0)
  const activeAbortRef = useRef<AbortController | null>(null)

  const loadAggregates = useCallback(async () => {
    const requestId = activeRequestRef.current + 1
    activeRequestRef.current = requestId
    activeAbortRef.current?.abort()
    const controller = new AbortController()
    activeAbortRef.current = controller

    setLoading(true)
    setError(null)
    setLoadingStageIndex(0)

    try {
      setLoadingStageIndex(1)
      const next = await fetchHistoryCostAggregates({
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
        include_archived: true,
      }, { signal: controller.signal })
      if (requestId !== activeRequestRef.current) return
      setLoadingStageIndex(2)
      setData(next)
      setLoadingStageIndex(3)
    } catch (err) {
      if (controller.signal.aborted || requestId !== activeRequestRef.current) return
      setError(err instanceof Error ? err.message : "Failed to load cost data")
    } finally {
      if (requestId === activeRequestRef.current) {
        activeAbortRef.current = null
        setLoading(false)
      }
    }
  }, [endDate, startDate])

  useEffect(() => {
    return () => {
      activeAbortRef.current?.abort()
    }
  }, [])

  useEffect(() => {
    void loadAggregates()
  }, [loadAggregates])

  function applyPreset(nextPreset: Exclude<PresetKey, "custom">) {
    const days = nextPreset === "5d" ? 5 : nextPreset === "30d" ? 30 : 90
    const range = buildPresetRange(days)
    setPreset(nextPreset)
    setStartDate(range.startDate)
    setEndDate(range.endDate)
  }

  const exportUrl = useMemo(
    () =>
      getHistoryCostExportUrl({
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
        granularity: exportGranularity,
        include_archived: true,
      }),
    [endDate, exportGranularity, startDate],
  )

  const totals = data?.totals

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[300px_170px_170px_140px_110px_130px] lg:items-end">
        <div className="inline-flex h-10 flex-wrap items-center gap-1.5 rounded-2xl border border-border/80 bg-card/50 p-1">
          <Button
            type="button"
            variant={preset === "5d" ? "default" : "ghost"}
            size="sm"
            className={preset === "5d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-foreground hover:bg-surface-3/80 hover:text-foreground"}
            onClick={() => applyPreset("5d")}
          >
            Last 5 days
          </Button>
          <Button
            type="button"
            variant={preset === "30d" ? "default" : "ghost"}
            size="sm"
            className={preset === "30d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-foreground hover:bg-surface-3/80 hover:text-foreground"}
            onClick={() => applyPreset("30d")}
          >
            Last 30 days
          </Button>
          <Button
            type="button"
            variant={preset === "90d" ? "default" : "ghost"}
            size="sm"
            className={preset === "90d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-foreground hover:bg-surface-3/80 hover:text-foreground"}
            onClick={() => applyPreset("90d")}
          >
            Last 90 days
          </Button>
        </div>
        <label className={`${fieldLabelClass} min-w-0`}>
          <span className="text-muted">Start date</span>
          <input
            type="date"
            value={startDate}
            onChange={(event) => {
              setPreset("custom")
              setStartDate(event.target.value)
            }}
            className={fieldControlClass}
          />
        </label>
        <label className={`${fieldLabelClass} min-w-0`}>
          <span className="text-muted">End date</span>
          <input
            type="date"
            value={endDate}
            onChange={(event) => {
              setPreset("custom")
              setEndDate(event.target.value)
            }}
            className={fieldControlClass}
          />
        </label>
        <label className={`${fieldLabelClass} min-w-0`}>
          <span className="text-muted">Export</span>
          <select
            value={exportGranularity}
            onChange={(event) => setExportGranularity(event.target.value as DbCostExportGranularity)}
            className={fieldControlClass}
          >
            <option value="day">Daily CSV</option>
            <option value="week">Weekly CSV</option>
            <option value="month">Monthly CSV</option>
          </select>
        </label>
        <Button
          type="button"
          variant="secondary"
          onClick={() => void loadAggregates()}
          disabled={loading}
          className="h-10 rounded-lg border border-border bg-surface-2/80 px-3.5 text-foreground hover:bg-surface-3"
        >
          {loading ? <Spinner size="sm" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
        <Button type="button" asChild className="h-10 rounded-lg px-3.5 shadow-sm">
          <a href={exportUrl} download>
            <Download className="h-4 w-4" />
            Export CSV
          </a>
        </Button>
      </div>

      {loading && (
        <div className="rounded-lg border border-border/80 bg-card/70 px-3 py-2">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-foreground">
              <Spinner size="sm" />
              <span>Loading cost analytics</span>
            </div>
            <span className="text-xs text-muted">{loadingStages[loadingStageIndex]}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full bg-intent-primary transition-all duration-300"
              style={{ width: `${((loadingStageIndex + 1) / loadingStages.length) * 100}%` }}
            />
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-intent-danger-border bg-intent-danger-subtle px-4 py-3 text-sm text-intent-danger">
          {error}
        </div>
      )}

      {loading ? (
        <CostsLoadingSkeleton />
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-muted">Total cost</div>
              <div className="mt-2 text-2xl font-semibold text-foreground">
                {totals ? formatUsd(totals.total_cost_usd) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-muted">Total calls</div>
              <div className="mt-2 text-2xl font-semibold text-foreground">
                {totals ? formatInteger(totals.total_calls) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-muted">Input tokens</div>
              <div className="mt-2 text-2xl font-semibold text-foreground">
                {totals ? formatInteger(totals.total_tokens_in) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-muted">Workflows</div>
              <div className="mt-2 text-2xl font-semibold text-foreground">
                {data ? formatInteger(data.workflow_count) : "--"}
              </div>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <BucketSection title="Daily spend" rows={data?.by_day ?? []} />
            <BucketSection title="Weekly spend" rows={data?.by_week ?? []} />
            <BucketSection title="Monthly spend" rows={data?.by_month ?? []} />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <GroupSection title="Top workflows" rows={data?.by_workflow ?? []} />
            <GroupSection title="Top phases" rows={data?.by_phase ?? []} />
            <GroupSection title="Top models" rows={data?.by_model ?? []} />
          </div>
        </>
      )}
    </div>
  )
}

export function GlobalCostOpsDialog({ open, onOpenChange }: GlobalCostOpsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl border-border bg-surface-2 p-0 text-foreground">
        <DialogHeader className="border-b border-border px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogTitle className="flex items-center gap-2 text-foreground">
                <CalendarDays className="h-5 w-5 text-intent-primary" />
                Costs
              </DialogTitle>
              <DialogDescription className="mt-1 text-muted">
                Real LLM spend over time from `cost_records` across all registry-linked run databases.
              </DialogDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => onOpenChange(false)}
                className="rounded-xl border border-transparent text-muted hover:border-border hover:bg-surface-3/70 hover:text-foreground"
                aria-label="Close costs modal"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-5 px-6 py-5">
          <CostsPanel />
        </div>
      </DialogContent>
    </Dialog>
  )
}
