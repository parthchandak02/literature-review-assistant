import { useState } from "react"
import * as Popover from "@radix-ui/react-popover"
import { ChevronDown, Clock, RotateCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Spinner } from "@/components/ui/feedback"
import type { HistoryEntry } from "@/lib/api"
import { formatShortDate } from "@/lib/format"
import { humanizeStatus } from "@/lib/humanize"
import { reusableConfigRuns } from "./reuseConfig"

interface ReuseConfigPopoverProps {
  history: HistoryEntry[]
  onSelect: (entry: HistoryEntry) => void
  loadingHistoryId: string | null
  disabled?: boolean
}

export function ReuseConfigPopover({ history, onSelect, loadingHistoryId, disabled = false }: ReuseConfigPopoverProps) {
  const [open, setOpen] = useState(false)
  const runs = reusableConfigRuns(history)
  const loading = Boolean(loadingHistoryId)

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled || loading}>
          {loading ? <Spinner size="sm" /> : <RotateCcw />}
          {loading ? "Loading config..." : "Reuse past config"}
          <ChevronDown className={open ? "rotate-180 transition-transform" : "transition-transform"} />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          className="z-50 w-[min(400px,calc(100vw-2rem))] overflow-hidden glass-panel-strong border border-border/80 rounded-panel shadow-xl"
        >
          <Command className="bg-transparent">
            <CommandInput
              placeholder="Search past reviews..."
              aria-label="Search past reviews"
              className="h-9 py-0 text-xs text-foreground placeholder:text-muted"
            />
            <CommandList className="max-h-72 overflow-y-auto">
              <CommandEmpty className="px-3 py-4 text-xs text-muted">
                {runs.length === 0
                  ? "No past reviews yet. Configs from reviews you start will show up here."
                  : "No reviews match your search."}
              </CommandEmpty>
              {runs.length > 0 && (
                <CommandGroup>
                  {runs.map((entry) => (
                    <CommandItem
                      key={entry.workflow_id}
                      value={`${entry.topic} ${entry.workflow_id}`}
                      onSelect={() => {
                        setOpen(false)
                        onSelect(entry)
                      }}
                      className="flex items-start gap-2.5 rounded-control px-2 py-2 text-left cursor-pointer data-[selected=true]:bg-surface-2"
                    >
                      <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs text-foreground leading-snug">{entry.topic}</span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-2xs text-muted">
                          {formatShortDate(entry.created_at)}
                          {entry.status !== "completed" && (
                            <Badge size="sm" variant="neutral">
                              {humanizeStatus(entry.status)}
                            </Badge>
                          )}
                        </span>
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
