import { formatCollapsedWorkflowBadge } from "@/lib/format"

export function CollapsedWorkflowBadge({
  workflowId,
}: {
  workflowId?: string | null
}) {
  const badge = formatCollapsedWorkflowBadge(workflowId)
  if (!badge) {
    return (
      <span
        className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-intent-danger-border bg-intent-danger-subtle text-[10px] font-bold text-intent-danger"
        title={workflowId ?? "Invalid workflow id"}
      >
        ERR
      </span>
    )
  }
  return (
    <span
      className="sidebar-wf-badge-collapsed inline-flex h-7 w-7 items-center justify-center rounded-md text-[15px] font-bold tabular-nums"
      title={workflowId ?? undefined}
    >
      #{badge}
    </span>
  )
}

export function ExpandedWorkflowBadge({
  workflowId,
}: {
  workflowId?: string | null
}) {
  const badge = formatCollapsedWorkflowBadge(workflowId)
  if (!badge) return null
  return (
    <span
      className="sidebar-wf-badge inline-flex h-6 min-w-8 items-center justify-center rounded-[7px] px-1.5 text-xs font-bold tabular-nums shrink-0"
      title={workflowId ?? undefined}
    >
      #{badge}
    </span>
  )
}
