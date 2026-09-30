import { ArrowUpDown, Search, Undo2 } from "lucide-react"
import { formatCount } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { FilterChip } from "@/components/ui/filter-chip"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SCREENING_FILTERS,
  SCREENING_FILTER_LABELS,
  SCREENING_SORT_LABELS,
  type ScreeningFilter,
  type ScreeningSort,
} from "./screeningModel"
import { ScreeningShortcutsHelp } from "./ScreeningShortcutsHelp"

export type { ScreeningFilter } from "./screeningModel"

export interface ScreeningFiltersBarProps {
  filter: ScreeningFilter
  counts: Record<ScreeningFilter, number>
  search: string
  sort: ScreeningSort
  visibleCount: number
  selectedVisibleCount: number
  selectedCount: number
  canUndo: boolean
  helpOpen: boolean
  onFilterChange: (filter: ScreeningFilter) => void
  onSearchChange: (search: string) => void
  onSortChange: (sort: ScreeningSort) => void
  onSelectAllVisible: (selected: boolean) => void
  onBulkDecide: (decision: "include" | "exclude") => void
  onBulkClear: () => void
  onUndo: () => void
  onHelpOpenChange: (open: boolean) => void
  readOnly?: boolean
}

export function ScreeningFiltersBar({
  filter,
  counts,
  search,
  sort,
  visibleCount,
  selectedVisibleCount,
  selectedCount,
  canUndo,
  helpOpen,
  onFilterChange,
  onSearchChange,
  onSortChange,
  onSelectAllVisible,
  onBulkDecide,
  onBulkClear,
  onUndo,
  onHelpOpenChange,
  readOnly = false,
}: ScreeningFiltersBarProps) {
  const allVisibleSelected = visibleCount > 0 && selectedVisibleCount === visibleCount
  const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <div role="group" aria-label="Filter by final decision" className="flex items-center gap-1 flex-wrap">
          <span aria-hidden className="text-xs text-muted pr-1">
            Final decision
          </span>
          {SCREENING_FILTERS.filter(
            (f) =>
              (f !== "automated" || counts.automated > 0 || filter === f) &&
              (!readOnly || f !== "overridden" || filter === f),
          ).map((f) => (
            <FilterChip
              key={f}
              active={filter === f}
              onClick={() => onFilterChange(f)}
              className="pointer-coarse:min-h-8"
            >
              {SCREENING_FILTER_LABELS[f]}
              <span className="tabular-nums text-muted">{formatCount(counts[f])}</span>
            </FilterChip>
          ))}
        </div>
        <div className="relative flex-1 min-w-48">
          <Search aria-hidden className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted" />
          <Input
            type="search"
            aria-label="Search titles and authors"
            placeholder="Search titles and authors"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" size="xs" variant="outline" aria-label={`Sort: ${SCREENING_SORT_LABELS[sort]}`}>
              <ArrowUpDown aria-hidden />
              {SCREENING_SORT_LABELS[sort]}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuRadioGroup value={sort} onValueChange={(v) => onSortChange(v as ScreeningSort)}>
              {(Object.keys(SCREENING_SORT_LABELS) as ScreeningSort[]).map((s) => (
                <DropdownMenuRadioItem key={s} value={s}>
                  {SCREENING_SORT_LABELS[s]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-2 flex-wrap text-xs">
        {!readOnly && (
        <label className="flex items-center gap-2 px-3 text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            ref={(el) => {
              if (el) el.indeterminate = someVisibleSelected
            }}
            disabled={visibleCount === 0}
            onChange={() => onSelectAllVisible(!allVisibleSelected)}
            className="size-4 accent-intent-primary cursor-pointer"
          />
          Select all matching
        </label>
        )}
        {!readOnly && selectedCount > 0 && (
          <>
            <span className="text-muted tabular-nums">{selectedCount} selected</span>
            <Button type="button" size="xs" variant="outline" onClick={() => onBulkDecide("include")}>
              Include selected
            </Button>
            <Button type="button" size="xs" variant="outline" onClick={() => onBulkDecide("exclude")}>
              Exclude selected
            </Button>
            <Button type="button" size="xs" variant="ghost" onClick={onBulkClear}>
              Clear overrides
            </Button>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          {!readOnly && (
            <Button type="button" size="xs" variant="ghost" disabled={!canUndo} onClick={onUndo} title="Undo (u)">
              <Undo2 aria-hidden />
              Undo
            </Button>
          )}
          <ScreeningShortcutsHelp open={helpOpen} onOpenChange={onHelpOpenChange} readOnly={readOnly} />
        </div>
      </div>
    </div>
  )
}
