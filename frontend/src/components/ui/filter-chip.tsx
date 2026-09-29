import * as React from "react"
import { cn } from "@/lib/utils"

export interface FilterChipProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "aria-pressed"> {
  active: boolean
}

/** Single-select filter chip. Only the selected chip is filled; hover and focus never add a fill. */
export function FilterChip({ active, className, type = "button", ...props }: FilterChipProps) {
  return (
    <button
      type={type}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors motion-reduce:transition-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        active
          ? "border-intent-primary-border bg-intent-primary-subtle text-intent-primary-text"
          : "border-border bg-transparent text-muted hover:text-foreground",
        className,
      )}
      {...props}
    />
  )
}
