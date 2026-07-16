import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CalendarDays, X } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import {
  fetchHistoryCostAggregates,
  getHistoryCostExportUrl,
} from "@/lib/api"
import type {
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
import {
  buildPresetRange,
  formatInteger,
  formatUsd,
  loadingStages,
  statCardClass,
  toApiEnd,
  toApiStart,
} from "@/components/cost-ops/costOpsFormatters"
import { cn } from "@/lib/utils"
import { CostOpsFiltersBar } from "@/components/cost-ops/CostOpsFiltersBar"
import {
  CostOpsBucketSection,
  CostOpsGroupSection,
  CostsLoadingSkeleton,
} from "@/components/cost-ops/CostOpsChartSection"

type PresetKey = "5d" | "30d" | "90d" | "custom"

interface GlobalCostOpsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
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
      <CostOpsFiltersBar
        preset={preset}
        startDate={startDate}
        endDate={endDate}
        exportGranularity={exportGranularity}
        exportUrl={exportUrl}
        loading={loading}
        onPresetChange={applyPreset}
        onStartDateChange={(value) => {
          setPreset("custom")
          setStartDate(value)
        }}
        onEndDateChange={(value) => {
          setPreset("custom")
          setEndDate(value)
        }}
        onExportGranularityChange={setExportGranularity}
        onRefresh={() => void loadAggregates()}
      />

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
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-xs uppercase tracking-wide text-muted">Total cost</div>
              <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                {totals ? formatUsd(totals.total_cost_usd) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-xs uppercase tracking-wide text-muted">Total calls</div>
              <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                {totals ? formatInteger(totals.total_calls) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-xs uppercase tracking-wide text-muted">Input tokens</div>
              <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                {totals ? formatInteger(totals.total_tokens_in) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-xs uppercase tracking-wide text-muted">Workflows</div>
              <div className="mt-2 text-lg sm:text-2xl font-semibold text-foreground tabular-nums truncate">
                {data ? formatInteger(data.workflow_count) : "--"}
              </div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            <CostOpsBucketSection title="Daily spend" rows={data?.by_day ?? []} />
            <CostOpsBucketSection title="Weekly spend" rows={data?.by_week ?? []} />
            <CostOpsBucketSection title="Monthly spend" rows={data?.by_month ?? []} />
          </div>

          <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
            <CostOpsGroupSection title="Top workflows" rows={data?.by_workflow ?? []} />
            <CostOpsGroupSection title="Top phases" rows={data?.by_phase ?? []} />
            <CostOpsGroupSection title="Top models" rows={data?.by_model ?? []} />
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
