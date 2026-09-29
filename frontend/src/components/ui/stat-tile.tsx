import * as React from "react"

import { cn } from "@/lib/utils"

export interface StatTileProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: React.ElementType
  label: React.ReactNode
  value: React.ReactNode
  sub?: React.ReactNode
  /** Hover text for the value, e.g. the exact count behind a compact "599.7K". */
  valueTitle?: string
  iconClassName?: string
  valueClassName?: string
}

const StatTile = React.forwardRef<HTMLDivElement, StatTileProps>(
  ({ icon: Icon, label, value, sub, valueTitle, iconClassName, valueClassName, className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("glass-panel rounded-panel border p-4 min-w-0 flex flex-col gap-1", className)}
      {...props}
    >
      <div className="flex items-center gap-2 min-w-0">
        {Icon && <Icon className={cn("h-4 w-4 shrink-0 text-muted", iconClassName)} aria-hidden />}
        <span className="label-caps truncate">{label}</span>
      </div>
      <div
        data-slot="stat-value"
        className={cn(
          "min-w-0 truncate text-2xl font-semibold text-foreground tabular-nums",
          valueClassName,
        )}
        title={valueTitle ?? (typeof value === "string" ? value : undefined)}
      >
        {value}
      </div>
      {sub != null && (
        <div className="label-muted min-w-0 [overflow-wrap:anywhere]">
          {sub}
        </div>
      )}
    </div>
  ),
)
StatTile.displayName = "StatTile"

export { StatTile }
