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
          className={cn(
            "glass-chip inline-flex items-center gap-1 max-w-full",
            "text-foreground",
          )}
        >
          <span className="text-muted shrink-0">{filter.label}:</span>
          <span className="truncate max-w-[10rem]">{filter.value}</span>
          <button
            type="button"
            onClick={() => onRemove(filter.id)}
            className="shrink-0 text-muted hover:text-foreground transition-colors"
            aria-label={`Remove ${filter.label} filter`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={onClearAll}
        className="text-xs text-intent-primary hover:text-intent-primary transition-colors whitespace-nowrap shrink-0"
      >
        Clear all
      </button>
    </div>
  )
}
