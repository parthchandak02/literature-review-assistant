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
  toApiEnd,
  toApiStart,
} from "@/components/cost-ops/costOpsFormatters"
import type { ChartTableMode } from "@/components/cost-ops/ChartTableToggle"
import { cn } from "@/lib/utils"
import { StatStrip, StatTile } from "@/components/ui/stat-tile"
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

const compactTileClass = "gap-0.5 px-2.5 py-2"
const compactValueClass = "text-sm"

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
          <StatStrip breakpoint="sm">
            <StatTile
              variant="inline"
              className={compactTileClass}
              valueClassName={compactValueClass}
              label="Total cost"
              value={totals ? formatUsd(totals.total_cost_usd) : "--"}
            />
            <StatTile
              variant="inline"
              className={compactTileClass}
              valueClassName={compactValueClass}
              tone={totals ? "primary" : "neutral"}
              label="Total calls"
              value={totals ? formatInteger(totals.total_calls) : "--"}
            />
            <StatTile
              variant="inline"
              className={compactTileClass}
              valueClassName={compactValueClass}
              label="Input tokens"
              value={totals ? formatCompact(totals.total_tokens_in) : "--"}
              valueTitle={totals ? `${formatInteger(totals.total_tokens_in)} tokens` : undefined}
            />
            <StatTile
              variant="inline"
              className={compactTileClass}
              valueClassName={compactValueClass}
              label="Reviews"
              value={data ? formatInteger(data.workflow_count) : "--"}
            />
          </StatStrip>

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
