import { ChevronDown, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { ResumeOption } from "@/lib/activityPhaseState"
import { milestoneForPhase } from "@/lib/constants"

interface ResumeOptionGroup {
  key: string
  label: string
  options: ResumeOption[]
}

function groupOptions(options: ResumeOption[]): ResumeOptionGroup[] {
  const groups: ResumeOptionGroup[] = []
  for (const option of options) {
    const milestone = milestoneForPhase(option.phase)
    const key = milestone?.key ?? option.phase
    const last = groups[groups.length - 1]
    if (last && last.key === key) last.options.push(option)
    else groups.push({ key, label: milestone?.label ?? option.label, options: [option] })
  }
  return groups
}

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
          <DropdownMenuLabel>Resume from phase</DropdownMenuLabel>
          {groupOptions(options).map((group) => (
            <DropdownMenuGroup key={group.key} aria-labelledby={`resume-group-${group.key}`}>
              <div
                id={`resume-group-${group.key}`}
                className="px-2 pt-2 pb-0.5 text-2xs font-semibold text-muted"
              >
                {group.label}
              </div>
              {group.options.map((option) => (
                <DropdownMenuItem
                  key={option.phase}
                  className="pl-5"
                  disabled={!option.selectable}
                  onSelect={() => onSelect(option.phase)}
                  title={option.title}
                >
                  {option.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
