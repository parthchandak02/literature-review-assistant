import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  fetchHistoryCostAggregates,
  getHistoryCostExportUrl,
} from "@/lib/api"
import type {
  HistoryCostAggregatesResponse,
} from "@/lib/api"
import {
  type CostOpsPresetKey,
  formatInteger,
  formatUsd,
  costOpsGridClass,
  resolveCostOpsPreset,
  statCardClass,
  toApiEnd,
  toApiStart,
} from "@/components/cost-ops/costOpsFormatters"
import type { ChartTableMode } from "@/components/cost-ops/ChartTableToggle"
import { cn } from "@/lib/utils"
import { useHistory } from "@/hooks/useHistory"
import { CostOpsFiltersBar } from "@/components/cost-ops/CostOpsFiltersBar"
import { describeReviewGroup, formatCompact } from "@/components/cost-ops/costBreakdown"
import {
  CostOpsGroupSection,
  CostOpsModelSection,
  CostOpsPhaseSection,
  CostOpsSpendSection,
  CostsLoadingState,
} from "@/components/cost-ops/CostOpsChartSection"

type PresetKey = CostOpsPresetKey

export function CostsPanel() {
  const [preset, setPreset] = useState<PresetKey>("all")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [chartTableMode, setChartTableMode] = useState<ChartTableMode>("chart")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<HistoryCostAggregatesResponse | null>(null)
  const historyQuery = useHistory({ refetchInterval: false })
  const topicByWorkflow = useMemo(
    () => new Map((historyQuery.data ?? []).map((entry) => [entry.workflow_id, entry.topic])),
    [historyQuery.data],
  )
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

    try {
      const next = await fetchHistoryCostAggregates({
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
        include_archived: true,
      }, { signal: controller.signal })
      if (requestId !== activeRequestRef.current) return
      setData(next)
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
    const range = resolveCostOpsPreset(nextPreset)
    setPreset(nextPreset)
    setStartDate(range.startDate)
    setEndDate(range.endDate)
  }

  const exportUrl = useMemo(
    () =>
      getHistoryCostExportUrl({
        start_ts: toApiStart(startDate),
        end_ts: toApiEnd(endDate),
        granularity: "day",
        include_archived: true,
      }),
    [endDate, startDate],
  )

  const totals = data?.totals

  return (
    <div className="@container space-y-2.5">
      <CostOpsFiltersBar
        preset={preset}
        startDate={startDate}
        endDate={endDate}
        exportUrl={exportUrl}
        loading={loading}
        chartTableMode={chartTableMode}
        onChartTableModeChange={setChartTableMode}
        onPresetChange={applyPreset}
        onStartDateChange={(value) => {
          setPreset("custom")
          setStartDate(value)
        }}
        onEndDateChange={(value) => {
          setPreset("custom")
          setEndDate(value)
        }}
        onRefresh={() => void loadAggregates()}
      />

      {error && (
        <div className="rounded-lg border border-intent-danger-border bg-intent-danger-subtle px-3 py-2 text-xs text-intent-danger">
          {error}
        </div>
      )}

      {loading && !data ? (
        <CostsLoadingState />
      ) : (
        <div
          aria-busy={loading}
          className={cn(
            "space-y-2.5 transition-opacity motion-reduce:transition-none",
            loading && "opacity-60",
          )}
        >
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-2xs uppercase tracking-wide text-muted">Total cost</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {totals ? formatUsd(totals.total_cost_usd) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-2xs uppercase tracking-wide text-muted">Total calls</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {totals ? formatInteger(totals.total_calls) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-2xs uppercase tracking-wide text-muted">Input tokens</div>
              <div
                className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate"
                title={totals ? `${formatInteger(totals.total_tokens_in)} tokens` : undefined}
              >
                {totals ? formatCompact(totals.total_tokens_in) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-2xs uppercase tracking-wide text-muted">Reviews</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {data ? formatInteger(data.workflow_count) : "--"}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <CostOpsSpendSection
              byDay={data?.by_day ?? []}
              byWeek={data?.by_week ?? []}
              byMonth={data?.by_month ?? []}
              viewMode={chartTableMode}
            />
            <div className={costOpsGridClass}>
              <CostOpsGroupSection
                className="@2xl:col-span-2 @6xl:col-span-1"
                title="Top reviews"
                labelHeader="Review"
                rows={data?.by_workflow ?? []}
                viewMode={chartTableMode}
                describeGroup={(id) => describeReviewGroup(id, topicByWorkflow.get(id))}
              />
              <CostOpsPhaseSection title="Top phases" rows={data?.by_phase ?? []} viewMode={chartTableMode} />
              <CostOpsModelSection title="Top models" rows={data?.by_model ?? []} viewMode={chartTableMode} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
