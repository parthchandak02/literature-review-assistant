import { cn } from "@/lib/utils"
import { formatCollapsedWorkflowBadge } from "@/lib/format"
import { STATUS_VARIANT, type RunStatus } from "@/lib/constants"
import type { BadgeVariant } from "@/components/ui/badge"

const TINT: Record<BadgeVariant, string> = {
  neutral: "sidebar-wf-badge",
  primary: "border border-intent-primary-border bg-intent-primary-subtle text-intent-primary-text",
  success: "border border-intent-success-border bg-intent-success-subtle text-intent-success-text",
  warning: "border border-intent-warning-border bg-intent-warning-subtle text-intent-warning-text",
  danger: "border border-intent-danger-border bg-intent-danger-subtle text-intent-danger-text",
  info: "border border-intent-info-border bg-intent-info-subtle text-intent-info-text",
  active: "border border-intent-active-border bg-intent-active-subtle text-intent-active",
}

function statusTint(status?: RunStatus) {
  return cn("inline-flex items-center", status ? TINT[STATUS_VARIANT[status]] : TINT.neutral)
}

export function CollapsedWorkflowBadge({
  workflowId,
  status,
}: {
  workflowId?: string | null
  status?: RunStatus
}) {
  const badge = formatCollapsedWorkflowBadge(workflowId)
  if (!badge) {
    return (
      <span
        className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-intent-danger-border bg-intent-danger-subtle text-2xs font-bold text-intent-danger"
        aria-hidden
      >
        ERR
      </span>
    )
  }
  return (
    <span
      className={cn(
        statusTint(status),
        "h-7 w-7 justify-center rounded-md p-0 text-xs font-bold tabular-nums",
      )}
      aria-hidden
    >
      #{badge}
    </span>
  )
}

export function ExpandedWorkflowBadge({
  workflowId,
  status,
}: {
  workflowId?: string | null
  status?: RunStatus
}) {
  const badge = formatCollapsedWorkflowBadge(workflowId)
  if (!badge) return null
  return (
    <span
      className={cn(
        statusTint(status),
        "h-6 min-w-8 justify-center rounded-md px-1.5 text-xs font-bold tabular-nums shrink-0",
      )}
      aria-hidden
    >
      #{badge}
    </span>
  )
}
