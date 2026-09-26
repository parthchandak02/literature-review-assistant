import { ConfirmDialog } from "@/components/ConfirmDialog"

export interface DeleteConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  workflowId: string | null
  onConfirm: (workflowId: string) => Promise<void>
}

export function DeleteConfirmDialog({
  open,
  onOpenChange,
  workflowId,
  onConfirm,
}: DeleteConfirmDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Delete review"
      description="Delete this review and all its data? This cannot be undone."
      confirmLabel="Delete"
      pendingLabel="Deleting..."
      onConfirm={async () => {
        if (workflowId) await onConfirm(workflowId)
      }}
    />
  )
}
