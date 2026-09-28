import { useId } from "react"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { cn } from "@/lib/utils"
import type { ReviewTypeChoice } from "./types"

const OPTIONS: { value: ReviewTypeChoice; title: string; description: string }[] = [
  {
    value: "systematic",
    title: "Systematic review",
    description: "Answers a focused question with appraised evidence (PICO, PRISMA 2020).",
  },
  {
    value: "scoping",
    title: "Scoping review",
    description: "Maps what evidence exists and where the gaps are (PCC, PRISMA-ScR).",
  },
]

interface ReviewTypeCardsProps {
  value: ReviewTypeChoice | null
  onChange: (value: ReviewTypeChoice) => void
  disabled?: boolean
  labelledBy: string
}

export function ReviewTypeCards({ value, onChange, disabled = false, labelledBy }: ReviewTypeCardsProps) {
  const baseId = useId()
  return (
    <RadioGroup
      value={value ?? ""}
      onValueChange={(v) => onChange(v as ReviewTypeChoice)}
      disabled={disabled}
      aria-labelledby={labelledBy}
      className="grid-cols-1 sm:grid-cols-2"
    >
      {OPTIONS.map((option) => {
        const id = `${baseId}-${option.value}`
        const selected = value === option.value
        return (
          <label
            key={option.value}
            htmlFor={id}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-panel border px-3 py-3 transition-colors",
              selected
                ? "border-intent-primary-border bg-intent-primary-subtle"
                : "border-border bg-card hover:bg-surface-2",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <RadioGroupItem id={id} value={option.value} className="mt-0.5" aria-describedby={`${id}-desc`} />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-foreground">{option.title}</span>
              <span id={`${id}-desc`} className="mt-0.5 block text-xs text-muted leading-relaxed">
                {option.description}
              </span>
            </span>
          </label>
        )
      })}
    </RadioGroup>
  )
}
