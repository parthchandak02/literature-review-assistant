import * as Popover from "@radix-ui/react-popover"
import { Keyboard } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SCREENING_SHORTCUTS } from "./screeningKeyboard"

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="inline-flex min-w-5 items-center justify-center rounded-control border border-border-strong bg-surface-2 px-1 font-mono text-2xs text-foreground">
      {children}
    </kbd>
  )
}

export interface ScreeningShortcutsHelpProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ScreeningShortcutsHelp({ open, onOpenChange }: ScreeningShortcutsHelpProps) {
  return (
    <Popover.Root open={open} onOpenChange={onOpenChange}>
      <Popover.Trigger asChild>
        <Button type="button" variant="ghost" size="xs" aria-label="Keyboard shortcuts">
          <Keyboard aria-hidden />
          <span className="hidden sm:inline">
            <Kbd>j</Kbd>/<Kbd>k</Kbd> move · <Kbd>i</Kbd>/<Kbd>e</Kbd> decide · <Kbd>?</Kbd> more
          </span>
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="end"
          sideOffset={6}
          aria-label="Keyboard shortcuts"
          className="z-50 w-64 glass-panel-strong border border-border rounded-panel p-3 shadow-lg"
        >
          <p className="text-xs font-semibold text-foreground mb-2">Keyboard shortcuts</p>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
            {SCREENING_SHORTCUTS.map(({ keys, label }) => (
              <div key={label} className="contents">
                <dt className="flex items-center gap-1">
                  {keys.map((k) => (
                    <Kbd key={k}>{k}</Kbd>
                  ))}
                </dt>
                <dd className="text-muted">{label}</dd>
              </div>
            ))}
          </dl>
          <p className="text-2xs text-muted mt-2">Shortcuts pause while you type in a field.</p>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
