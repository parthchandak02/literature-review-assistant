import { useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import { ChevronDown } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { FilterComboboxPopover } from "@/components/database/FilterComboboxPopover"
import { facetOptions, type FacetOption } from "@/components/database/facetOptions"
import { FACET_LABELS, type MultiFacetKey } from "@/hooks/useDbFilters"
import type { PapersFacets, PapersQuery } from "@/lib/api/db"
import { cn } from "@/lib/utils"

const FACET_ORDER: MultiFacetKey[] = ["ta", "ft", "primaryStatus", "source", "country"]

export interface FacetFiltersProps {
  filters: PapersQuery
  facets: PapersFacets | undefined
  onToggleFacet: (key: MultiFacetKey, value: string) => void
  onClearFacet: (key: MultiFacetKey) => void
  onYearRange: (min: number | null, max: number | null) => void
  onTitleFilterChange: (v: string) => void
  onAuthorFilterChange: (v: string) => void
  onTitleSuggestQuery: (q: string) => void
  onAuthorSuggestQuery: (q: string) => void
  titleSuggestions: string[]
  authorSuggestions: string[]
  isLoadingTitleSuggestions: boolean
  isLoadingAuthorSuggestions: boolean
}

export function FacetFilters({
  filters,
  facets,
  onToggleFacet,
  onClearFacet,
  onYearRange,
  onTitleFilterChange,
  onAuthorFilterChange,
  onTitleSuggestQuery,
  onAuthorSuggestQuery,
  titleSuggestions,
  authorSuggestions,
  isLoadingTitleSuggestions,
  isLoadingAuthorSuggestions,
}: FacetFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter papers">
      <FilterComboboxPopover
        label="Title"
        value={filters.title}
        onChange={onTitleFilterChange}
        placeholder="Search titles..."
        serverSuggestions={titleSuggestions}
        onSuggestionQuery={onTitleSuggestQuery}
        isLoadingSuggestions={isLoadingTitleSuggestions}
      />
      <FilterComboboxPopover
        label="Authors"
        value={filters.author}
        onChange={onAuthorFilterChange}
        placeholder="Search authors..."
        serverSuggestions={authorSuggestions}
        onSuggestionQuery={onAuthorSuggestQuery}
        isLoadingSuggestions={isLoadingAuthorSuggestions}
      />
      <YearRangeFilter
        yearMin={filters.yearMin}
        yearMax={filters.yearMax}
        years={(facets?.counts?.year ?? []).map((c) => Number(c.value)).filter(Number.isFinite)}
        onApply={onYearRange}
      />
      {FACET_ORDER.map((key) => (
        <FacetMenu
          key={key}
          facetKey={key}
          label={FACET_LABELS[key]}
          selected={filters[key]}
          options={facetOptions(key, facets, filters[key])}
          onToggle={(value) => onToggleFacet(key, value)}
          onClear={() => onClearFacet(key)}
        />
      ))}
    </div>
  )
}

function TriggerLabel({ label, count }: { label: string; count: number }) {
  return (
    <>
      {label}
      {count > 0 && (
        <Badge variant="primary" size="sm" className="min-w-4 justify-center px-1 tabular-nums">
          {count}
        </Badge>
      )}
      <ChevronDown className="opacity-60" />
    </>
  )
}

interface FacetMenuProps {
  facetKey: MultiFacetKey
  label: string
  selected: string[]
  options: FacetOption[]
  onToggle: (value: string) => void
  onClear: () => void
}

export function FacetMenu({ facetKey, label, selected, options, onToggle, onClear }: FacetMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="secondary"
          size="xs"
          className={cn(selected.length > 0 && "border border-intent-primary-border")}
          data-facet={facetKey}
        >
          <TriggerLabel label={label} count={selected.length} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-60 overflow-y-auto">
        <DropdownMenuLabel>{label}</DropdownMenuLabel>
        {options.length === 0 ? (
          <div className="px-2 py-1.5 text-xs text-muted">No values yet.</div>
        ) : (
          options.map((opt) => (
            <DropdownMenuCheckboxItem
              key={opt.value}
              checked={selected.includes(opt.value)}
              onSelect={(e) => e.preventDefault()}
              onCheckedChange={() => onToggle(opt.value)}
              className="text-xs"
            >
              <span className="min-w-0 flex-1 truncate" title={opt.label}>
                {opt.label}
              </span>
              <span className="ml-auto font-mono text-2xs tabular-nums text-muted">
                {opt.count.toLocaleString()}
              </span>
            </DropdownMenuCheckboxItem>
          ))
        )}
        {selected.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onClear} className="text-xs text-intent-primary-text">
              Clear {label.toLowerCase()}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

interface YearRangeFilterProps {
  yearMin: number | null
  yearMax: number | null
  years: number[]
  onApply: (min: number | null, max: number | null) => void
}

function parseYearInput(raw: string): number | null {
  const n = Number.parseInt(raw.trim(), 10)
  return Number.isFinite(n) ? n : null
}

function YearRangeFilter({ yearMin, yearMax, years, onApply }: YearRangeFilterProps) {
  const [open, setOpen] = useState(false)
  const [minText, setMinText] = useState("")
  const [maxText, setMaxText] = useState("")
  const active = yearMin != null || yearMax != null
  const lo = years.length ? Math.min(...years) : null
  const hi = years.length ? Math.max(...years) : null

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setMinText(yearMin != null ? String(yearMin) : "")
      setMaxText(yearMax != null ? String(yearMax) : "")
    }
    setOpen(next)
  }

  const apply = () => {
    let min = parseYearInput(minText)
    let max = parseYearInput(maxText)
    if (min != null && max != null && min > max) [min, max] = [max, min]
    onApply(min, max)
    setOpen(false)
  }

  const label = active
    ? yearMin != null && yearMax != null
      ? `Year ${yearMin}–${yearMax}`
      : yearMin != null
        ? `Year ≥ ${yearMin}`
        : `Year ≤ ${yearMax}`
    : "Year"

  const inputClass =
    "w-20 rounded-control border border-border-strong bg-background px-2 py-1 text-xs text-foreground font-mono tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

  return (
    <Popover.Root open={open} onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <Button
          type="button"
          variant="secondary"
          size="xs"
          className={cn(active && "border border-intent-primary-border")}
        >
          {label}
          <ChevronDown className="opacity-60" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="z-50 w-64 rounded-panel border border-border glass-panel-strong p-3 shadow-lg"
        >
          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              apply()
            }}
          >
            <div className="label-caps">Publication year</div>
            <div className="flex items-center gap-2 text-xs">
              <label className="flex flex-col gap-1">
                <span className="text-muted">From</span>
                <input
                  inputMode="numeric"
                  value={minText}
                  onChange={(e) => setMinText(e.target.value)}
                  placeholder={lo != null ? String(lo) : "Any"}
                  aria-label="From year"
                  className={inputClass}
                />
              </label>
              <span className="mt-5 text-muted">–</span>
              <label className="flex flex-col gap-1">
                <span className="text-muted">To</span>
                <input
                  inputMode="numeric"
                  value={maxText}
                  onChange={(e) => setMaxText(e.target.value)}
                  placeholder={hi != null ? String(hi) : "Any"}
                  aria-label="To year"
                  className={inputClass}
                />
              </label>
            </div>
            <div className="flex justify-end gap-1.5">
              {active && (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    onApply(null, null)
                    setOpen(false)
                  }}
                >
                  Clear
                </Button>
              )}
              <Button type="submit" size="xs">
                Apply
              </Button>
            </div>
          </form>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
