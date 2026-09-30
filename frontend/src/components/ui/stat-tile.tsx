import * as React from "react"

import { cn } from "@/lib/utils"

export type StatTone = "neutral" | "success" | "info" | "warning" | "danger" | "primary"

const TONE_TEXT: Record<StatTone, string> = {
  neutral: "text-foreground",
  success: "text-intent-success-text",
  info: "text-intent-info-text",
  warning: "text-intent-warning-text",
  danger: "text-intent-danger-text",
  primary: "text-intent-primary-text",
}

export interface StatTileProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: React.ElementType
  label: React.ReactNode
  value: React.ReactNode
  sub?: React.ReactNode
  /** Hover text for the value, e.g. the exact count behind a compact "599.7K". */
  valueTitle?: string
  /** Semantic tone for counts. Spend stays neutral. */
  tone?: StatTone
  /** `inline` drops the glass box so several tiles can share one `StatStrip`. */
  variant?: "tile" | "inline"
  iconClassName?: string
  valueClassName?: string
}

const StatTile = React.forwardRef<HTMLDivElement, StatTileProps>(
  (
    {
      icon: Icon,
      label,
      value,
      sub,
      valueTitle,
      tone = "neutral",
      variant = "tile",
      iconClassName,
      valueClassName,
      className,
      ...props
    },
    ref,
  ) => (
    <div
      ref={ref}
      data-slot="stat-tile"
      className={cn(
        "min-w-0 flex flex-col gap-1",
        variant === "tile" ? "glass-panel rounded-panel border p-4" : "px-4 py-3",
        className,
      )}
      {...props}
    >
      <div className="flex items-center gap-2 min-w-0">
        {Icon && (
          <Icon
            className={cn("h-4 w-4 shrink-0", tone === "neutral" ? "text-muted" : TONE_TEXT[tone], iconClassName)}
            aria-hidden
          />
        )}
        <span className="label-caps truncate">{label}</span>
      </div>
      <div
        data-slot="stat-value"
        className={cn(
          "num min-w-0 truncate font-semibold",
          variant === "tile" ? "text-2xl" : "text-xl",
          TONE_TEXT[tone],
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

const STRIP_LAYOUT = {
  sm: "sm:grid-cols-none sm:grid-flow-col sm:auto-cols-[minmax(0,1fr)] max-sm:[&>*:nth-child(even)]:border-l max-sm:[&>*:nth-child(n+3)]:border-t sm:[&>*:not(:first-child)]:border-l",
  lg: "lg:grid-cols-none lg:grid-flow-col lg:auto-cols-[minmax(0,1fr)] max-lg:[&>*:nth-child(even)]:border-l max-lg:[&>*:nth-child(n+3)]:border-t lg:[&>*:not(:first-child)]:border-l",
} as const

export interface StatStripProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Width at which the 2-column stack becomes one row. */
  breakpoint?: keyof typeof STRIP_LAYOUT
}

/** One glass panel holding inline `StatTile`s, split by 1px dividers. */
const StatStrip = React.forwardRef<HTMLDivElement, StatStripProps>(
  ({ breakpoint = "lg", className, ...props }, ref) => (
    <div
      ref={ref}
      data-slot="stat-strip"
      className={cn(
        "glass-panel rounded-panel border grid grid-cols-2 overflow-hidden [&>*]:border-border",
        STRIP_LAYOUT[breakpoint],
        className,
      )}
      {...props}
    />
  ),
)
StatStrip.displayName = "StatStrip"

export { StatStrip, StatTile }
