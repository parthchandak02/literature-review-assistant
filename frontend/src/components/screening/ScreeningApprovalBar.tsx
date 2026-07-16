import { CheckCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"

export interface ScreeningApprovalBarProps {
  approved: boolean
  approving: boolean
  overrideCount: number
  onApprove: () => void
}

export function ScreeningApprovalBar({
  approved,
  approving,
  overrideCount,
  onApprove,
}: ScreeningApprovalBarProps) {
  if (approved) {
    return (
      <div className="flex items-center gap-2 p-3 rounded-lg bg-intent-success-subtle border border-intent-success-border text-sm text-intent-success">
        <CheckCircle className="h-4 w-4" />
        Screening approved -- workflow is resuming extraction...
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <Button
        onClick={onApprove}
        disabled={approving}
        variant="warning"
        className={cn(
          "h-10 px-4 rounded-lg text-sm",
          approving && "cursor-not-allowed",
        )}
      >
        {approving && <Spinner size="sm" />}
        {approving ? "Approving..." : "Approve Screening and Resume Extraction"}
      </Button>
      {overrideCount > 0 && (
        <span className="text-xs text-intent-primary font-medium">
          {overrideCount} override{overrideCount !== 1 ? "s" : ""} will be sent for active learning
        </span>
      )}
    </div>
  )
}
