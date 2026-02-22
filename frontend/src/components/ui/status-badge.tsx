import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// RunStatus type -- mirrors the SSE status values used across the app
// ---------------------------------------------------------------------------

export type RunStatus = "idle" | "connecting" | "streaming" | "done" | "error" | "cancelled" | "stale"

export const STATUS_LABEL: Record<RunStatus, string> = {
  idle: "Ready",
  connecting: "Connecting",
  streaming: "Running",
  done: "Completed",
  error: "Failed",
  cancelled: "Cancelled",
  stale: "Stale",
}

/** Map raw backend/SSE status strings to the canonical RunStatus. */
export function resolveRunStatus(raw: string | null | undefined): RunStatus {
  const s = (raw ?? "").toLowerCase()
  if (s === "completed" || s === "done") return "done"
  if (s === "running" || s === "streaming") return "streaming"
  if (s === "connecting") return "connecting"
  if (s === "error" || s === "failed") return "error"
  if (s === "cancelled" || s === "canceled" || s === "interrupted") return "cancelled"
  if (s === "stale") return "stale"
  return "idle"
}

// ---------------------------------------------------------------------------
// StatusBadge -- pill badge with colored dot
// ---------------------------------------------------------------------------

const BADGE_STYLE: Record<RunStatus, string> = {
  idle: "text-zinc-400 bg-zinc-800/60 border-zinc-700",
  connecting: "text-violet-400 bg-violet-500/10 border-violet-500/20",
  streaming: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  done: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  error: "text-red-400 bg-red-500/10 border-red-500/20",
  cancelled: "text-zinc-400 bg-zinc-800/60 border-zinc-700",
  stale: "text-amber-500 bg-amber-500/10 border-amber-500/30",
}

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
