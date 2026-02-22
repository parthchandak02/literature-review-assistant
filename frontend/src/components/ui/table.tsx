import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ChevronLeft, ChevronRight } from "lucide-react"

// ---------------------------------------------------------------------------
// Th -- table header cell with optional filter popover
// ---------------------------------------------------------------------------

interface ThProps {
  children: React.ReactNode
  align?: "right"
  filter?: React.ReactNode
  className?: string
}

export function Th({ children, align, filter, className }: ThProps) {
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-xs font-medium text-zinc-500 uppercase tracking-wide",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {filter ? (
        <div className="flex items-center gap-1.5">
          <span>{children}</span>
          {filter}
        </div>
      ) : (
        children
      )}
    </th>
  )
}

// ---------------------------------------------------------------------------
// Td -- table data cell
// ---------------------------------------------------------------------------

interface TdProps {
  children: React.ReactNode
  className?: string
  align?: "right"
}

export function Td({ children, className, align }: TdProps) {
  return (
    <td
      className={cn(
        "px-4 py-2.5",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {children}
    </td>
  )
}

// ---------------------------------------------------------------------------
// TableSkeleton -- animated loading placeholder
// ---------------------------------------------------------------------------

interface TableSkeletonProps {
  /** Number of columns to render */
  cols: number
  /** Number of rows to render */
  rows: number
}

export function TableSkeleton({ cols, rows }: TableSkeletonProps) {
  return (
    <div className="p-4 space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3">
          {Array.from({ length: cols }).map((_, j) => (
            <div
              key={j}
              className="h-4 bg-zinc-800 rounded animate-pulse"
              style={{ flex: j === 0 ? 3 : 1 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination -- prev/next controls for server-side paginated tables
// ---------------------------------------------------------------------------

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPrev: () => void
  onNext: () => void
}

export function Pagination({ page, pageSize, total, onPrev, onNext }: PaginationProps) {
  const start = page * pageSize + 1
  const end = Math.min((page + 1) * pageSize, total)
  const hasPrev = page > 0
  const hasNext = end < total

  if (total <= pageSize) return null

  return (
    <div className="flex items-center justify-between text-xs text-zinc-500">
      <span>
        {start}-{end} of {total.toLocaleString()}
      </span>
      <div className="flex gap-1">
        <Button
          size="sm"
          variant="outline"
          onClick={onPrev}
          disabled={!hasPrev}
          className="h-7 w-7 p-0 border-zinc-800"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onNext}
          disabled={!hasNext}
          className="h-7 w-7 p-0 border-zinc-800"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
