import { Download, RefreshCw } from "lucide-react"
import type { DbCostExportGranularity } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { cn } from "@/lib/utils"
import { fieldControlClass, fieldLabelClass } from "./costOpsFormatters"

type PresetKey = "5d" | "30d" | "90d" | "custom"

const PRESET_BUTTON_CLASS = (active: boolean) =>
  cn(
    "h-8 rounded-xl px-3 text-sm shrink-0",
    active
      ? "shadow-sm"
      : "text-foreground hover:bg-surface-3/80 hover:text-foreground",
  )

export interface CostOpsFiltersBarProps {
  preset: PresetKey
  startDate: string
  endDate: string
  exportGranularity: DbCostExportGranularity
  exportUrl: string
  loading: boolean
  onPresetChange: (preset: Exclude<PresetKey, "custom">) => void
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
  onExportGranularityChange: (value: DbCostExportGranularity) => void
  onRefresh: () => void
}

export function CostOpsFiltersBar({
  preset,
  startDate,
  endDate,
  exportGranularity,
  exportUrl,
  loading,
  onPresetChange,
  onStartDateChange,
  onEndDateChange,
  onExportGranularityChange,
  onRefresh,
}: CostOpsFiltersBarProps) {
  return (
    <div className="flex flex-col gap-4">
      {/* Presets: full-width row so wrapped pills never overlap content below */}
      <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-border/80 bg-card/50 p-1.5 w-full">
        <Button
          type="button"
          variant={preset === "5d" ? "default" : "ghost"}
          size="sm"
          className={PRESET_BUTTON_CLASS(preset === "5d")}
          onClick={() => onPresetChange("5d")}
        >
          Last 5 days
        </Button>
        <Button
          type="button"
          variant={preset === "30d" ? "default" : "ghost"}
          size="sm"
          className={PRESET_BUTTON_CLASS(preset === "30d")}
          onClick={() => onPresetChange("30d")}
        >
          Last 30 days
        </Button>
        <Button
          type="button"
          variant={preset === "90d" ? "default" : "ghost"}
          size="sm"
          className={PRESET_BUTTON_CLASS(preset === "90d")}
          onClick={() => onPresetChange("90d")}
        >
          Last 90 days
        </Button>
      </div>

      {/* Date + export fields: fluid grid, no fixed pixel columns */}
      <div className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-3">
        <label className={cn(fieldLabelClass, "min-w-0")}>
          <span className="text-muted">Start date</span>
          <input
            type="date"
            value={startDate}
            onChange={(event) => onStartDateChange(event.target.value)}
            className={fieldControlClass}
          />
        </label>
        <label className={cn(fieldLabelClass, "min-w-0")}>
          <span className="text-muted">End date</span>
          <input
            type="date"
            value={endDate}
            onChange={(event) => onEndDateChange(event.target.value)}
            className={fieldControlClass}
          />
        </label>
        <label className={cn(fieldLabelClass, "min-w-0 min-[480px]:col-span-2 lg:col-span-1")}>
          <span className="text-muted">Export</span>
          <select
            value={exportGranularity}
            onChange={(event) => onExportGranularityChange(event.target.value as DbCostExportGranularity)}
            className={fieldControlClass}
          >
            <option value="day">Daily CSV</option>
            <option value="week">Weekly CSV</option>
            <option value="month">Monthly CSV</option>
          </select>
        </label>
      </div>

      {/* Actions: wrap on narrow widths */}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={onRefresh}
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
    </div>
  )
}
