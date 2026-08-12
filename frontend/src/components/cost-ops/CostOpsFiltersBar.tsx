import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  costOpsSegmentButtonClass,
  costOpsSegmentGroupClass,
  fieldControlClass,
  fieldLabelClass,
  type CostOpsPresetKey,
} from "./costOpsFormatters"
import { CostOpsToolbar } from "./CostOpsToolbar"
import type { ChartTableMode } from "./ChartTableToggle"

export interface CostOpsFiltersBarProps {
  preset: CostOpsPresetKey
  startDate: string
  endDate: string
  exportUrl: string
  loading: boolean
  showPresets?: boolean
  chartTableMode: ChartTableMode
  onChartTableModeChange: (mode: ChartTableMode) => void
  onPresetChange: (preset: Exclude<CostOpsPresetKey, "custom">) => void
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
  onRefresh: () => void
}

export function CostOpsFiltersBar({
  preset,
  startDate,
  endDate,
  exportUrl,
  loading,
  showPresets = true,
  chartTableMode,
  onChartTableModeChange,
  onPresetChange,
  onStartDateChange,
  onEndDateChange,
  onRefresh,
}: CostOpsFiltersBarProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex flex-wrap items-end gap-2 min-w-0 flex-1">
          {showPresets && (
            <div className={costOpsSegmentGroupClass}>
              {(["all", "5d", "30d", "90d"] as const).map((key) => (
                <Button
                  key={key}
                  type="button"
                  variant="ghost"
                  size="sm"
                  className={costOpsSegmentButtonClass(preset === key)}
                  onClick={() => onPresetChange(key)}
                >
                  {key === "all" ? "All" : key}
                </Button>
              ))}
            </div>
          )}
          <label className={cn(fieldLabelClass, "min-w-[8.5rem]")}>
            <span className="text-muted">Start</span>
            <input
              type="date"
              value={startDate}
              disabled={preset === "all"}
              onChange={(event) => onStartDateChange(event.target.value)}
              className={cn(fieldControlClass, preset === "all" && "opacity-60")}
            />
          </label>
          <label className={cn(fieldLabelClass, "min-w-[8.5rem]")}>
            <span className="text-muted">End</span>
            <input
              type="date"
              value={endDate}
              disabled={preset === "all"}
              onChange={(event) => onEndDateChange(event.target.value)}
              className={cn(fieldControlClass, preset === "all" && "opacity-60")}
            />
          </label>
        </div>

        <CostOpsToolbar
          chartTableMode={chartTableMode}
          onChartTableModeChange={onChartTableModeChange}
          exportUrl={exportUrl}
          loading={loading}
          onRefresh={onRefresh}
        />
      </div>
    </div>
  )
}
