import { Download, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { costOpsSegmentButtonClass } from "./costOpsFormatters"
import { ChartTableToggle, type ChartTableMode } from "./ChartTableToggle"

export interface CostOpsToolbarProps {
  chartTableMode: ChartTableMode
  onChartTableModeChange: (mode: ChartTableMode) => void
  exportUrl: string
  loading: boolean
  onRefresh: () => void
}

export function CostOpsToolbar({
  chartTableMode,
  onChartTableModeChange,
  exportUrl,
  loading,
  onRefresh,
}: CostOpsToolbarProps) {
  return (
    <ChartTableToggle
      mode={chartTableMode}
      onChange={onChartTableModeChange}
      ariaLabel="Cost breakdown display and actions"
    >
      <span className="mx-0.5 h-5 w-px bg-border/80" aria-hidden />
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRefresh}
        disabled={loading}
        className={costOpsSegmentButtonClass(false)}
      >
        {loading ? <Spinner size="sm" /> : <RefreshCw className="h-3.5 w-3.5" />}
        Refresh
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        asChild
        className={costOpsSegmentButtonClass(false)}
      >
        <a href={exportUrl} download>
          <Download className="h-3.5 w-3.5" />
          Export CSV
        </a>
      </Button>
    </ChartTableToggle>
  )
}
