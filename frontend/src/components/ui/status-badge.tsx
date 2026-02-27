import { cn } from "@/lib/utils"
import {
  type RunStatus,
  STATUS_LABEL,
  BADGE_STYLE,
  resolveRunStatus,
} from "@/lib/constants"

// Re-export shared types and helpers for backwards compatibility.
export type { RunStatus }
export { resolveRunStatus, STATUS_LABEL }

// ---------------------------------------------------------------------------
// StatusBadge -- pill badge with colored dot
// ---------------------------------------------------------------------------

interface StatusBadgeProps {
  status: RunStatus | string
  className?: string
  /** Override the display label */
  label?: string
}

export function StatusBadge({ status, className, label }: StatusBadgeProps) {
  const resolved = resolveRunStatus(status)
  const displayLabel = label ?? STATUS_LABEL[resolved]
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border w-fit",
        BADGE_STYLE[resolved],
        className,
      )}
    >
      {displayLabel}
    </span>
  )
}
