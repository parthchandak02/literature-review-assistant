import { useEffect, useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Spinner } from "@/components/ui/feedback"
import { cn } from "@/lib/utils"
import { ChevronDown, Filter, X } from "lucide-react"
import { Button } from "@/components/ui/button"

export const SUGGEST_DEBOUNCE_MS = 200
export const FILTER_DEBOUNCE_MS = 350

export interface FilterComboboxPopoverProps {
  value: string
  onChange: (v: string) => void
  placeholder: string
  /** Toolbar panel: show labeled field trigger instead of icon-only. */
  label?: string
  /** Categorical columns: pass all distinct values, filtered client-side by query. */
  staticSuggestions?: string[]
  /** Text columns: parent provides server-fetched suggestions. */
  serverSuggestions?: string[]
  /** Called with the debounced query so parent can fetch server suggestions. */
  onSuggestionQuery?: (q: string) => void
  isLoadingSuggestions?: boolean
}

export function FilterComboboxPopover({
  value,
  onChange,
  placeholder,
  label,
  staticSuggestions,
  serverSuggestions,
  onSuggestionQuery,
  isLoadingSuggestions = false,
}: FilterComboboxPopoverProps) {
  const [open, setOpen] = useState(false)
  const [local, setLocal] = useState(value)
  const isActive = value !== ""

  useEffect(() => {
    setLocal(value)
  }, [value])

  useEffect(() => {
    if (!onSuggestionQuery) return
    const t = setTimeout(() => onSuggestionQuery(local), SUGGEST_DEBOUNCE_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local])

  useEffect(() => {
    const t = setTimeout(() => onChange(local), FILTER_DEBOUNCE_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [local])

  const suggestions = staticSuggestions
    ? staticSuggestions.filter((s) => s.toLowerCase().includes(local.toLowerCase()))
    : (serverSuggestions ?? [])

  const applyValue = (v: string) => {
    setLocal(v)
    onChange(v)
    setOpen(false)
  }

  const clearValue = () => {
    setLocal("")
    onChange("")
    if (onSuggestionQuery) onSuggestionQuery("")
    setOpen(false)
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        {label ? (
          <Button
            type="button"
            variant="secondary"
            size="xs"
            className={cn("max-w-56", isActive && "border border-intent-primary-border")}
            aria-label={`Filter ${label}`}
            title={value || undefined}
          >
            <span>{label}</span>
            {value && <span className="truncate text-muted">: {value}</span>}
            <ChevronDown className="opacity-60" />
          </Button>
        ) : (
          <button
            type="button"
            className={cn(
              "flex items-center justify-center h-4 w-4 rounded transition-colors",
              isActive
                ? "text-intent-primary hover:text-intent-primary"
                : "text-muted hover:text-foreground",
            )}
            aria-label="Filter column"
          >
            <Filter className="h-3 w-3" />
          </button>
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          onInteractOutside={() => setOpen(false)}
          className={cn(
            "z-50 w-56 glass-panel-strong border border-border/80 rounded-panel shadow-2xl shadow-black/60",
            "overflow-hidden",
          )}
        >
          <Command shouldFilter={false}>
            <div className="relative flex items-center border-b border-border/80 px-2 glass-toolbar">
              <CommandInput
                value={local}
                onValueChange={(v) => setLocal(v)}
                placeholder={placeholder}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    onChange(local)
                    setOpen(false)
                  }
                  if (e.key === "Escape") {
                    setOpen(false)
                  }
                }}
                className="border-0 focus:ring-0 h-8 text-xs bg-transparent text-foreground placeholder:text-muted py-0"
              />
              {local && (
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    clearValue()
                  }}
                  className="shrink-0 text-muted hover:text-foreground transition-colors ml-1"
                  aria-label="Clear filter"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            <CommandList>
              {isLoadingSuggestions && (
                <div className="py-2 px-3 text-xs text-muted flex items-center gap-2">
                  <Spinner size="sm" />
                  Loading...
                </div>
              )}
              {!isLoadingSuggestions && suggestions.length === 0 && local && (
                <CommandEmpty className="py-3 text-xs text-muted">No matches.</CommandEmpty>
              )}
              {suggestions.length > 0 && (
                <CommandGroup>
                  {suggestions.map((s) => (
                    <CommandItem
                      key={s}
                      value={s}
                      onSelect={() => applyValue(s)}
                      className={cn(
                        "text-xs text-foreground cursor-pointer rounded-control px-2 py-1.5",
                        "data-[selected=true]:bg-intent-primary-subtle data-[selected=true]:text-intent-primary",
                      )}
                    >
                      <span className="truncate">{s}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
          <Popover.Arrow className="fill-surface-2" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
