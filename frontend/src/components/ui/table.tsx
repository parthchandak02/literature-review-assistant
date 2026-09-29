import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ChevronsUpDown } from "lucide-react"

// ---------------------------------------------------------------------------
// Th -- table header cell with optional filter popover or sort button
// ---------------------------------------------------------------------------

export type SortDirection = "asc" | "desc"

function ariaSortValue(
  direction: SortDirection | null | undefined,
): "ascending" | "descending" | "none" {
  if (direction === "asc") return "ascending"
  if (direction === "desc") return "descending"
  return "none"
}

interface SortButtonProps {
  children: React.ReactNode
  direction: SortDirection | null | undefined
  onSort: () => void
  className?: string
}

/** Header sort toggle: label plus a chevron that shows the active direction. */
export function SortButton({ children, direction, onSort, className }: SortButtonProps) {
  const Icon = direction === "asc" ? ChevronUp : direction === "desc" ? ChevronDown : ChevronsUpDown
  return (
    <button
      type="button"
      onClick={onSort}
      className={cn(
        "-mx-1 inline-flex items-center gap-1 rounded-control px-1 py-0.5 uppercase tracking-wide transition-colors",
        "hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        direction ? "text-foreground" : "text-muted",
        className,
      )}
    >
      <span>{children}</span>
      <Icon className={cn("h-3 w-3 shrink-0", !direction && "opacity-60")} aria-hidden />
    </button>
  )
}

interface ThProps {
  children: React.ReactNode
  align?: "right"
  filter?: React.ReactNode
  className?: string
  /** Renders the label as a sort button and sets aria-sort. */
  sortable?: boolean
  sortDirection?: SortDirection | null
  onSort?: () => void
  /** Override aria-sort for headers that host their own sort buttons. */
  ariaSort?: "ascending" | "descending" | "none"
  scope?: "col" | "row"
}

export function Th({
  children,
  align,
  filter,
  className,
  sortable,
  sortDirection,
  onSort,
  ariaSort,
  scope = "col",
}: ThProps) {
  const label =
    sortable && onSort ? (
      <SortButton direction={sortDirection} onSort={onSort}>
        {children}
      </SortButton>
    ) : (
      children
    )
  return (
    <th
      scope={scope}
      aria-sort={ariaSort ?? (sortable ? ariaSortValue(sortDirection) : undefined)}
      className={cn(
        "px-4 py-2.5 text-xs font-medium text-foreground uppercase tracking-wide",
        align === "right" ? "text-right" : "text-left",
        className,
      )}
    >
      {filter ? (
        <div className="flex items-center gap-1.5">
          <span>{label}</span>
          {filter}
        </div>
      ) : (
        label
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
        "px-4 py-2.5 text-foreground",
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
              className="h-4 rounded animate-pulse bg-surface-3/50"
              style={{ flex: j === 0 ? 3 : 1 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pagination -- range, count, optional page size, prev/next for server-side tables
// ---------------------------------------------------------------------------

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPrev: () => void
  onNext: () => void
  /** Noun after the count, e.g. "papers". */
  itemLabel?: string
  /** Inline hint rendered after the count, e.g. an InfoHint. */
  labelHint?: ReactNode
  pageSizeOptions?: readonly number[]
  onPageSizeChange?: (size: number) => void
  className?: string
}

function formatPageRange(page: number, pageSize: number, total: number): string {
  if (total <= 0) return "0"
  const start = Math.min(page * pageSize + 1, total)
  const end = Math.min((page + 1) * pageSize, total)
  return `${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()}`
}

export function Pagination({
  page,
  pageSize,
  total,
  onPrev,
  onNext,
  itemLabel,
  labelHint,
  pageSizeOptions,
  onPageSizeChange,
  className,
}: PaginationProps) {
  const hasPrev = page > 0
  const hasNext = (page + 1) * pageSize < total
  const multiPage = total > pageSize

  return (
    <div className={cn("flex flex-wrap items-center justify-between gap-2 text-xs text-muted", className)}>
      <span className="inline-flex items-center gap-1">
        <span className="tabular-nums" aria-live="polite">
          {formatPageRange(page, pageSize, total)}
          {itemLabel ? ` ${itemLabel}` : ""}
        </span>
        {labelHint}
      </span>
      <div className="flex items-center gap-3">
        {pageSizeOptions && onPageSizeChange && (
          <label className="flex items-center gap-1.5">
            <span>Rows per page</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded-control border border-border-strong bg-background px-1.5 py-0.5 text-xs text-foreground tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
        {multiPage && (
          <div className="flex gap-1">
            <Button
              size="icon-sm"
              variant="outline"
              onClick={onPrev}
              disabled={!hasPrev}
              className="border-border"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="icon-sm"
              variant="outline"
              onClick={onNext}
              disabled={!hasNext}
              className="border-border"
              aria-label="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
