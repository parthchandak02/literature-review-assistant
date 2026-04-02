import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CalendarDays, Download, Loader2, RefreshCw, Table2, X } from "lucide-react"
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
  "h-10 w-full min-w-0 rounded-lg border border-zinc-800 bg-zinc-950/90 px-3 text-sm text-zinc-100 shadow-sm outline-none transition-colors hover:border-zinc-700 focus:border-violet-500"
const statCardClass = "rounded-xl border border-zinc-800/80 bg-zinc-950/60 px-4 py-4"
const loadingStages = [
  "Preparing filters",
  "Querying costs",
  "Building summaries",
  "Rendering tables",
] as const
const sectionHeaderClass = "border-b border-zinc-800/80 px-4 py-3 text-sm font-semibold text-zinc-200"

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
    <div className="rounded-md border border-zinc-700 bg-zinc-900/95 px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 text-zinc-400">{label}</div>
      <div className="font-medium text-zinc-100">{formatUsd(value)}</div>
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
        <thead className="sticky top-0 bg-zinc-950/95 text-zinc-500">
          <tr>
            <th className="px-4 py-2 text-left font-medium">{labelHeader}</th>
            <th className="px-4 py-2 text-right font-medium">Calls</th>
            <th className="px-4 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${labelHeader}-${row.label}`} className="border-t border-zinc-900 text-zinc-300">
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
    <div className="relative rounded-xl border border-zinc-800/80 bg-zinc-950/60">
      <div className={sectionHeaderClass}>
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-sm text-zinc-500">No cost records in this window.</div>
      ) : showRaw ? (
        <>
          <RawTable rows={rows} labelHeader={labelHeader} />
          <div className="border-t border-zinc-800/60 px-3 py-2">
            <div className="flex justify-end">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                className="h-8 rounded-lg border border-zinc-700 bg-zinc-900/70 px-3 text-zinc-200 hover:bg-zinc-800"
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
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                tickFormatter={(value: string) => (value.length > 12 ? `${value.slice(0, 12)}...` : value)}
                interval="preserveStartEnd"
                height={20}
              />
              <YAxis
                tick={{ fill: "#a1a1aa", fontSize: 11 }}
                tickFormatter={formatAxisCost}
                width={70}
              />
              <Tooltip content={<CostTooltip />} />
              <Bar dataKey="cost_usd" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {!showRaw && rows.length > 0 && (
        <div className="border-t border-zinc-800/60 px-3 py-2">
          <div className="flex justify-end">
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-8 rounded-lg border border-zinc-700 bg-zinc-900/85 px-2.5 text-zinc-200 hover:bg-zinc-800"
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

export function GlobalCostOpsDialog({ open, onOpenChange }: GlobalCostOpsDialogProps) {
  const defaultRange = useMemo(() => buildPresetRange(30), [])
  const [preset, setPreset] = useState<PresetKey>("30d")
  const [startDate, setStartDate] = useState(defaultRange.startDate)
  const [endDate, setEndDate] = useState(defaultRange.endDate)
  const [exportGranularity, setExportGranularity] = useState<DbCostExportGranularity>("day")
  const [loading, setLoading] = useState(false)
  const [loadingProgress, setLoadingProgress] = useState(0)
  const [loadingStageIndex, setLoadingStageIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<HistoryCostAggregatesResponse | null>(null)
  const activeRequestRef = useRef(0)
  const activeAbortRef = useRef<AbortController | null>(null)
  const stageIntervalRef = useRef<number | null>(null)

  const clearStageInterval = useCallback(() => {
    if (stageIntervalRef.current !== null) {
      window.clearInterval(stageIntervalRef.current)
      stageIntervalRef.current = null
    }
  }, [])

  const loadAggregates = useCallback(async () => {
    const requestId = activeRequestRef.current + 1
    activeRequestRef.current = requestId
    activeAbortRef.current?.abort()
    const controller = new AbortController()
    activeAbortRef.current = controller
    clearStageInterval()

    setLoading(true)
    setError(null)
    setLoadingStageIndex(0)
    setLoadingProgress(14)

    stageIntervalRef.current = window.setInterval(() => {
      setLoadingStageIndex((prev) => Math.min(prev + 1, loadingStages.length - 2))
      setLoadingProgress((prev) => Math.min(prev + 16, 88))
    }, 450)

    try {
      setLoadingStageIndex(1)
      setLoadingProgress(38)
      const next = await fetchHistoryCostAggregates({
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
        include_archived: true,
      }, { signal: controller.signal })
      if (requestId !== activeRequestRef.current) return
      setLoadingStageIndex(2)
      setLoadingProgress(82)
      setData(next)
      setLoadingStageIndex(3)
      setLoadingProgress(100)
    } catch (err) {
      if (controller.signal.aborted || requestId !== activeRequestRef.current) return
      setError(err instanceof Error ? err.message : "Failed to load cost data")
    } finally {
      if (requestId !== activeRequestRef.current) return
      clearStageInterval()
      activeAbortRef.current = null
      setLoading(false)
    }
  }, [clearStageInterval, endDate, startDate])

  useEffect(() => {
    return () => {
      activeAbortRef.current?.abort()
      clearStageInterval()
    }
  }, [clearStageInterval])

  useEffect(() => {
    if (!open) return
    void loadAggregates()
  }, [loadAggregates, open])

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
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl border-zinc-800 bg-zinc-900 p-0 text-zinc-100">
        <DialogHeader className="border-b border-zinc-800 px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogTitle className="flex items-center gap-2 text-zinc-100">
                <CalendarDays className="h-5 w-5 text-violet-300" />
                Costs
              </DialogTitle>
              <DialogDescription className="mt-1 text-zinc-400">
                Real LLM spend over time from `cost_records` across all registry-linked run databases.
              </DialogDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => onOpenChange(false)}
                className="rounded-xl border border-transparent text-zinc-400 hover:border-zinc-800 hover:bg-zinc-800/70 hover:text-zinc-200"
                aria-label="Close costs modal"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-5 px-6 py-5">
          <div className="inline-flex flex-wrap gap-1.5 rounded-2xl border border-zinc-800/80 bg-zinc-950/50 p-1">
            <Button
              type="button"
              variant={preset === "5d" ? "default" : "ghost"}
              size="sm"
              className={preset === "5d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"}
              onClick={() => applyPreset("5d")}
            >
              Last 5 days
            </Button>
            <Button
              type="button"
              variant={preset === "30d" ? "default" : "ghost"}
              size="sm"
              className={preset === "30d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"}
              onClick={() => applyPreset("30d")}
            >
              Last 30 days
            </Button>
            <Button
              type="button"
              variant={preset === "90d" ? "default" : "ghost"}
              size="sm"
              className={preset === "90d" ? "h-8 rounded-xl px-3 shadow-sm" : "h-8 rounded-xl px-3 text-zinc-300 hover:bg-zinc-800/80 hover:text-zinc-100"}
              onClick={() => applyPreset("90d")}
            >
              Last 90 days
            </Button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_180px_auto]">
            <label className={`${fieldLabelClass} min-w-0`}>
              <span className="text-zinc-400">Start date</span>
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
              <span className="text-zinc-400">End date</span>
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
              <span className="text-zinc-400">Export</span>
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
            <div className="flex items-end gap-2 sm:col-span-2 xl:col-span-1 xl:justify-end">
              <Button
                type="button"
                variant="secondary"
                onClick={() => void loadAggregates()}
                disabled={loading}
                className="h-10 rounded-lg border border-zinc-700 bg-zinc-900/80 px-3.5 text-zinc-100 hover:bg-zinc-800"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Refresh
              </Button>
              <Button type="button" asChild className="h-10 rounded-lg px-3.5 shadow-sm">
                <a href={exportUrl} download>
                  <Download className="h-4 w-4" />
                  Export CSV
                </a>
              </Button>
            </div>
          </div>

          {loading && (
            <div className="rounded-xl border border-violet-900/40 bg-violet-950/20 px-4 py-3">
              <div className="mb-2 flex items-center justify-between text-sm text-violet-200">
                <span>{loadingStages[loadingStageIndex]}...</span>
                <span className="text-violet-300/80">{loadingProgress}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-900">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-violet-500 via-fuchsia-400 to-violet-500 transition-all duration-300"
                  style={{ width: `${loadingProgress}%` }}
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {loadingStages.map((stage, index) => {
                  const stateClass = index < loadingStageIndex
                    ? "border-violet-500/70 bg-violet-500/20 text-violet-100"
                    : index === loadingStageIndex
                      ? "border-fuchsia-400/70 bg-fuchsia-500/20 text-fuchsia-100"
                      : "border-zinc-700/80 bg-zinc-900/70 text-zinc-400"
                  return (
                    <span
                      key={stage}
                      className={`rounded-full border px-2.5 py-1 text-xs ${stateClass}`}
                    >
                      {stage}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-900/80 bg-red-950/40 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-4">
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Total cost</div>
              <div className="mt-2 text-2xl font-semibold text-zinc-50">
                {totals ? formatUsd(totals.total_cost_usd) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Total calls</div>
              <div className="mt-2 text-2xl font-semibold text-zinc-50">
                {totals ? formatInteger(totals.total_calls) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Input tokens</div>
              <div className="mt-2 text-2xl font-semibold text-zinc-50">
                {totals ? formatInteger(totals.total_tokens_in) : "--"}
              </div>
            </div>
            <div className={statCardClass}>
              <div className="text-xs uppercase tracking-wide text-zinc-500">Workflows</div>
              <div className="mt-2 text-2xl font-semibold text-zinc-50">
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
        </div>
      </DialogContent>
    </Dialog>
  )
}
