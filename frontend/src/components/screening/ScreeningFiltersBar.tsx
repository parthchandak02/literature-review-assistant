import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export type ScreeningFilter = "all" | "include" | "uncertain"

export interface ScreeningFiltersBarProps {
  filter: ScreeningFilter
  total: number
  includedCount: number
  uncertainCount: number
  onFilterChange: (filter: ScreeningFilter) => void
}

export function ScreeningFiltersBar({
  filter,
  total,
  includedCount,
  uncertainCount,
  onFilterChange,
}: ScreeningFiltersBarProps) {
  return (
    <div className="flex items-center gap-1 border-b border-border pb-0">
      {(["all", "include", "uncertain"] as const).map((f) => (
        <Button
          key={f}
          onClick={() => onFilterChange(f)}
          variant="ghost"
          size="sm"
          className={cn(
            "px-3 h-8 text-xs font-medium border-b-2 -mb-px capitalize rounded-none",
            filter === f
              ? "border-intent-primary text-intent-primary"
              : "border-transparent text-muted hover:text-foreground",
          )}
        >
          {f === "all"
            ? `All (${total})`
            : f === "include"
              ? `Include (${includedCount})`
              : `Uncertain (${uncertainCount})`}
        </Button>
      ))}
    </div>
  )
}
