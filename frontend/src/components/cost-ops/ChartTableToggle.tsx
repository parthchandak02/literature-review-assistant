import { BarChart3, Table2 } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  costOpsSegmentButtonClass,
  costOpsSegmentGroupClass,
} from "./costOpsFormatters"

export type ChartTableMode = "chart" | "table"

export interface ChartTableToggleProps {
  mode: ChartTableMode
  onChange: (mode: ChartTableMode) => void
  className?: string
}

/** Standalone chart/table segmented control (e.g. per-run Cost tab sections). */
export function ChartTableToggle({ mode, onChange, className }: ChartTableToggleProps) {
  return (
    <div className={cn(costOpsSegmentGroupClass, className)}>
      <button
        type="button"
        className={costOpsSegmentButtonClass(mode === "chart")}
        onClick={() => onChange("chart")}
        aria-pressed={mode === "chart"}
      >
        <BarChart3 className="h-3.5 w-3.5" />
        Chart
      </button>
      <button
        type="button"
        className={costOpsSegmentButtonClass(mode === "table")}
        onClick={() => onChange("table")}
        aria-pressed={mode === "table"}
      >
        <Table2 className="h-3.5 w-3.5" />
        Table
      </button>
    </div>
  )
}
