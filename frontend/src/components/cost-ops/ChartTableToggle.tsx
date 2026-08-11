import { BarChart3, Table2 } from "lucide-react"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { cn } from "@/lib/utils"

export type ChartTableMode = "chart" | "table"

export interface ChartTableToggleProps {
  mode: ChartTableMode
  onChange: (mode: ChartTableMode) => void
  className?: string
}

export function ChartTableToggle({ mode, onChange, className }: ChartTableToggleProps) {
  return (
    <GlassTabs
      items={[
        { id: "chart", label: "Chart", icon: BarChart3 },
        { id: "table", label: "Table", icon: Table2 },
      ]}
      activeTab={mode}
      onTabChange={onChange}
      className={cn(className)}
    />
  )
}
