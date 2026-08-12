import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { CalendarDays, X } from "lucide-react"
import {
  fetchHistoryCostAggregates,
  getHistoryCostExportUrl,
} from "@/lib/api"
import type {
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
import { CostOpsFiltersBar } from "@/components/cost-ops/CostOpsFiltersBar"
import {
  CostOpsGroupSection,
  CostOpsPhaseSection,
  CostOpsSpendSection,
  CostsLoadingState,
} from "@/components/cost-ops/CostOpsChartSection"

type PresetKey = CostOpsPresetKey

interface GlobalCostOpsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Standalone costs content panel -- can be rendered inside any container
 * (the SettingsDialog embeds it in its "Costs" tab).
 */
export function CostsPanel() {
  const [preset, setPreset] = useState<PresetKey>("all")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [chartTableMode, setChartTableMode] = useState<ChartTableMode>("chart")
  const [loading, setLoading] = useState(false)
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
    <div className="space-y-2.5">
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

      {loading ? (
        <CostsLoadingState />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-[10px] uppercase tracking-wide text-muted">Total cost</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {totals ? formatUsd(totals.total_cost_usd) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-[10px] uppercase tracking-wide text-muted">Total calls</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {totals ? formatInteger(totals.total_calls) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-[10px] uppercase tracking-wide text-muted">Input tokens</div>
              <div className="mt-0.5 text-sm font-semibold text-foreground tabular-nums truncate">
                {totals ? formatInteger(totals.total_tokens_in) : "--"}
              </div>
            </div>
            <div className={cn(statCardClass, "min-w-0")}>
              <div className="text-[10px] uppercase tracking-wide text-muted">Workflows</div>
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
              <CostOpsGroupSection title="Top workflows" rows={data?.by_workflow ?? []} viewMode={chartTableMode} axisLabelKind="workflow" />
              <CostOpsPhaseSection title="Top phases" rows={data?.by_phase ?? []} viewMode={chartTableMode} />
              <CostOpsGroupSection title="Top models" rows={data?.by_model ?? []} viewMode={chartTableMode} axisLabelKind="model" />
            </div>
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
