import { useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import { FilterComboboxPopover } from "@/components/database/FilterComboboxPopover"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Filter } from "lucide-react"

export interface DatabaseFiltersPopoverProps {
  activeCount: number
  titleFilter: string
  authorFilter: string
  yearFilter: string
  sourceFilter: string
  countryFilter: string
  taFilter: string
  ftFilter: string
  primaryStatusFilter: string
  onTitleFilterChange: (v: string) => void
  onAuthorFilterChange: (v: string) => void
  onYearFilterChange: (v: string) => void
  onSourceFilterChange: (v: string) => void
  onCountryFilterChange: (v: string) => void
  onTaFilterChange: (v: string) => void
  onFtFilterChange: (v: string) => void
  onPrimaryStatusFilterChange: (v: string) => void
  onTitleSuggestQuery: (q: string) => void
  onAuthorSuggestQuery: (q: string) => void
  titleSuggestions: string[]
  authorSuggestions: string[]
  isLoadingTitleSuggestions: boolean
  isLoadingAuthorSuggestions: boolean
  years: number[]
  sources: string[]
  countries: string[]
  taDecisions: string[]
  ftDecisions: string[]
  primaryStatuses: string[]
}

export function DatabaseFiltersPopover({
  activeCount,
  titleFilter,
  authorFilter,
  yearFilter,
  sourceFilter,
  countryFilter,
  taFilter,
  ftFilter,
  primaryStatusFilter,
  onTitleFilterChange,
  onAuthorFilterChange,
  onYearFilterChange,
  onSourceFilterChange,
  onCountryFilterChange,
  onTaFilterChange,
  onFtFilterChange,
  onPrimaryStatusFilterChange,
  onTitleSuggestQuery,
  onAuthorSuggestQuery,
  titleSuggestions,
  authorSuggestions,
  isLoadingTitleSuggestions,
  isLoadingAuthorSuggestions,
  years,
  sources,
  countries,
  taDecisions,
  ftDecisions,
  primaryStatuses,
}: DatabaseFiltersPopoverProps) {
  const [open, setOpen] = useState(false)

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="h-8 gap-1.5 shrink-0 text-xs"
        >
          <Filter className="h-3.5 w-3.5" />
          Filters
          {activeCount > 0 && (
            <Badge variant="primary" size="sm" className="tabular-nums px-1.5 min-w-5">
              {activeCount}
            </Badge>
          )}
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className={cn(
            "z-50 w-[min(100vw-2rem,20rem)] glass-panel-strong border border-border/80 rounded-xl",
            "shadow-2xl shadow-black/60 overflow-hidden",
          )}
        >
          <div className="px-3 py-2 border-b border-border/70 glass-toolbar">
            <div className="text-xs font-medium text-foreground">Filter papers</div>
            <div className="text-[10px] text-muted">All filters apply together.</div>
          </div>
          <div className="p-3 grid gap-2.5 max-h-[min(70vh,28rem)] overflow-y-auto">
            <FilterComboboxPopover
              label="Title"
              value={titleFilter}
              onChange={onTitleFilterChange}
              placeholder="Search titles..."
              serverSuggestions={titleSuggestions}
              onSuggestionQuery={onTitleSuggestQuery}
              isLoadingSuggestions={isLoadingTitleSuggestions}
            />
            <FilterComboboxPopover
              label="Authors"
              value={authorFilter}
              onChange={onAuthorFilterChange}
              placeholder="Search authors..."
              serverSuggestions={authorSuggestions}
              onSuggestionQuery={onAuthorSuggestQuery}
              isLoadingSuggestions={isLoadingAuthorSuggestions}
            />
            <FilterComboboxPopover
              label="Year"
              value={yearFilter}
              onChange={onYearFilterChange}
              placeholder="Filter year..."
              staticSuggestions={years.map(String)}
            />
            <FilterComboboxPopover
              label="Source"
              value={sourceFilter}
              onChange={onSourceFilterChange}
              placeholder="Filter source..."
              staticSuggestions={sources}
            />
            <FilterComboboxPopover
              label="Country"
              value={countryFilter}
              onChange={onCountryFilterChange}
              placeholder="Filter country..."
              staticSuggestions={countries}
            />
            <FilterComboboxPopover
              label="Title/Abstract"
              value={taFilter}
              onChange={onTaFilterChange}
              placeholder="include / exclude..."
              staticSuggestions={taDecisions}
            />
            <FilterComboboxPopover
              label="Full-Text"
              value={ftFilter}
              onChange={onFtFilterChange}
              placeholder="include / exclude..."
              staticSuggestions={ftDecisions}
            />
            <FilterComboboxPopover
              label="Primary Status"
              value={primaryStatusFilter}
              onChange={onPrimaryStatusFilterChange}
              placeholder="primary / secondary..."
              staticSuggestions={primaryStatuses}
            />
          </div>
          <Popover.Arrow className="fill-surface-2" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
