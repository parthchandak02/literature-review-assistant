import { ChevronDown, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { ResumeOption } from "@/lib/activityPhaseState"

export interface ResumeMenuProps {
  options: ResumeOption[]
  blockedReason: string | null
  disabled?: boolean
  onSelect: (phase: string) => void
}

export function ResumeMenu({ options, blockedReason, disabled = false, onSelect }: ResumeMenuProps) {
  const noneSelectable = !options.some((option) => option.selectable)
  const hint = blockedReason ?? (noneSelectable ? "No phase can be resumed yet." : null)
  const triggerDisabled = disabled || hint !== null

  return (
    <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
      {hint ? (
        <p id="resume-blocked-hint" className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={triggerDisabled}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={triggerDisabled}
            aria-describedby={hint ? "resume-blocked-hint" : undefined}
          >
            <RotateCcw aria-hidden />
            Resume from…
            <ChevronDown aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-56">
          <DropdownMenuLabel>Re-run from phase</DropdownMenuLabel>
          {options.map((option) => (
            <DropdownMenuItem
              key={option.phase}
              disabled={!option.selectable}
              onSelect={() => onSelect(option.phase)}
            >
              {option.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
