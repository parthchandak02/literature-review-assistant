import { cn } from "@/lib/utils"
import { STATUS_DOT, type RunStatus } from "@/lib/constants"
import { Spinner } from "@/components/ui/feedback"

/** Semantic status dot; optional ping for live/running states. */
export function StatusPulse({
  status,
  animate = false,
  size = "sm",
  className,
}: {
  status: RunStatus | "idle"
  animate?: boolean
  size?: "xs" | "sm"
  className?: string
}) {
  const dotSize = size === "xs" ? "h-1.5 w-1.5" : "h-2 w-2"
  const color = STATUS_DOT[status] ?? "bg-surface-4"

  if (animate) {
    return (
      <span className={cn("relative flex shrink-0", dotSize, className)} aria-hidden>
        <span
          className={cn(
            "status-pulse-ping animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
            color,
          )}
        />
        <span className={cn("relative inline-flex rounded-full h-full w-full", color)} />
      </span>
    )
  }

  return (
    <span
      className={cn("inline-flex rounded-full shrink-0", dotSize, color, className)}
      aria-hidden
    />
  )
}

/** Live SSE connection indicator for toolbars and data views. */
export function LiveStreamStatus({
  mode,
  label,
  className,
}: {
  mode: "connecting" | "streaming" | "compact"
  label?: string
  className?: string
}) {
  const text =
    label ??
    (mode === "connecting"
      ? "Connecting to event stream..."
      : mode === "compact"
        ? "Live"
        : "Live stream active")

  return (
    <div className={cn("flex items-center gap-1.5 text-xs text-intent-active", className)}>
      {mode === "connecting" ? (
        <Spinner size="sm" />
      ) : (
        <StatusPulse status="streaming" animate size="sm" />
      )}
      <span className="whitespace-nowrap">{text}</span>
    </div>
  )
}
