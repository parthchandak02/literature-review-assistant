import type { CSSProperties, ReactNode } from "react"
import { cn } from "@/lib/utils"

export interface ViewToolbarProps {
  title?: ReactNode
  actions?: ReactNode
  children?: ReactNode
  /** h-9 toolbar (default false uses h-11). */
  dense?: boolean
  bordered?: boolean
  sticky?: boolean
  className?: string
  style?: CSSProperties
}

/**
 * Canonical glass toolbar chrome for view headers.
 * Prefer children for fully custom layouts; title + actions for the common case.
 */
export function ViewToolbar({
  title,
  actions,
  children,
  dense = false,
  bordered = true,
  sticky = false,
  className,
  style,
}: ViewToolbarProps) {
  const hasTitleRow = title != null || actions != null

  return (
    <div
      style={style}
      className={cn(
        "glass-toolbar flex items-center gap-3 shrink-0",
        dense ? "h-9 px-4" : "h-11 px-4",
        bordered && "border-b border-border/70",
        sticky && "sticky top-0 z-30",
        hasTitleRow && !children && "justify-between",
        className,
      )}
    >
      {children ?? (
        <>
          {title != null ? (
            <div className="flex items-center gap-2 min-w-0 flex-1">{title}</div>
          ) : (
            <div className="flex-1 min-w-0" />
          )}
          {actions != null ? (
            <div className="flex items-center gap-2 shrink-0">{actions}</div>
          ) : null}
        </>
      )}
    </div>
  )
}
