import { cn } from "@/lib/utils"
import { STATUS_PROGRESS, type RunStatus } from "@/lib/constants"

export function CardProgressBar({
  status,
  progress,
}: {
  status: RunStatus
  progress?: number
}) {
  const colorClass = STATUS_PROGRESS[status] ?? "bg-surface-4"
  const isIndeterminate = progress === -1
  const showFill =
    !isIndeterminate &&
    (status === "streaming" || status === "connecting" || status === "done")
  const fillPercent = showFill ? (progress != null ? progress * 100 : status === "done" ? 100 : 0) : 0

  if (isIndeterminate) {
    return (
      <div className="h-0.5 overflow-hidden bg-surface-3/40">
        <div className="h-full w-1/3 rounded-full bg-intent-active/70 animate-pulse" />
      </div>
    )
  }

  return (
    <div
      className={cn(
        "h-0.5 overflow-hidden",
        showFill ? "bg-surface-3/40" : colorClass,
      )}
    >
      {showFill && (
        <div
          className={cn("h-full transition-all duration-300", colorClass)}
          style={{ width: `${fillPercent}%` }}
        />
      )}
    </div>
  )
}
