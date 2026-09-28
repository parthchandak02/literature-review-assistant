import { ConfirmDialog } from "@/components/ConfirmDialog"
import { formatCollapsedWorkflowBadge } from "@/lib/format"
import { truncateTopic } from "@/components/sidebar/historyRowModel"

export interface DeleteConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  workflowId: string | null
  topic?: string | null
  onConfirm: (workflowId: string) => Promise<void>
}

/** What DELETE /api/history/{id} removes: the registry row and the run directory. */
const REMOVED_ITEMS = [
  "The review database (search results, screening decisions, extracted data)",
  "Manuscript drafts, figures and the submission package",
  "Downloaded full-text PDFs",
  "Logs, config snapshot and all other run artifacts",
]

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  workflowId,
  topic,
  onConfirm,
}: DeleteConfirmDialogProps) {
  const badge = formatCollapsedWorkflowBadge(workflowId)
  const idText = badge ? ` (#${badge})` : ""
  const title = topic ? `Delete "${truncateTopic(topic, 60)}"${idText}?` : `Delete review${idText}?`

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={
        <>
          <p>This permanently removes:</p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
            {REMOVED_ITEMS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="mt-2 font-medium text-foreground">This cannot be undone.</p>
        </>
      }
      confirmLabel="Delete permanently"
      pendingLabel="Deleting..."
      onConfirm={async () => {
        if (workflowId) await onConfirm(workflowId)
      }}
    />
  )
}
