import { X } from "lucide-react"
import { cn } from "@/lib/utils"

export interface ActiveFilter {
  id: string
  label: string
  value: string
}

export interface FilterChipBarProps {
  filters: ActiveFilter[]
  onRemove: (id: string) => void
  onClearAll: () => void
}

export function FilterChipBar({ filters, onRemove, onClearAll }: FilterChipBarProps) {
  if (filters.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5 min-w-0">
      {filters.map((filter) => (
        <span
          key={filter.id}
          className={cn("glass-chip inline-flex items-center gap-1 max-w-full py-0 pr-0", "text-foreground")}
        >
          <span className="text-muted shrink-0">{filter.label}:</span>
          <span className="truncate max-w-40" title={filter.value}>
            {filter.value}
          </span>
          <button
            type="button"
            onClick={() => onRemove(filter.id)}
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-pill text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={`Remove ${filter.label} filter: ${filter.value}`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={onClearAll}
        className="min-h-6 rounded-control px-1 text-xs text-intent-primary hover:underline whitespace-nowrap shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Clear all
      </button>
    </div>
  )
}
