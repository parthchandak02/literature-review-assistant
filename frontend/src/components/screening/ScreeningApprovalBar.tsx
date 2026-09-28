import { AlertTriangle, CheckCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { pluralize } from "./screeningModel"

export type ApprovalStatus =
  | { kind: "idle" }
  | { kind: "approving" }
  | { kind: "resuming" }
  | { kind: "approveFailed"; message: string }
  | { kind: "resumeFailed"; message: string }
  | { kind: "done" }

export interface ScreeningApprovalBarProps {
  status: ApprovalStatus
  overrideCount: number
  onApprove: () => void
  onRetryResume: () => void
}

export function ScreeningApprovalBar({ status, overrideCount, onApprove, onRetryResume }: ScreeningApprovalBarProps) {
  if (status.kind === "done") {
    return (
      <div role="status" className="flex items-center gap-2 text-sm text-intent-success-text">
        <CheckCircle aria-hidden className="size-4" />
        Screening approved. Extraction is starting.
      </div>
    )
  }

  if (status.kind === "resumeFailed" || status.kind === "resuming") {
    return (
      <div className="flex items-center gap-3 flex-wrap">
        {status.kind === "resumeFailed" && (
          <div role="alert" className="flex items-start gap-2 text-sm text-intent-danger-text flex-1 min-w-0">
            <AlertTriangle aria-hidden className="size-4 mt-0.5 shrink-0" />
            <span>
              Screening approved, but the run didn&apos;t resume: {status.message}
            </span>
          </div>
        )}
        <Button
          type="button"
          size="lg"
          className="ml-auto"
          disabled={status.kind === "resuming"}
          onClick={onRetryResume}
        >
          {status.kind === "resuming" && <Spinner size="sm" />}
          {status.kind === "resuming" ? "Resuming..." : "Retry resume"}
        </Button>
      </div>
    )
  }

  const approving = status.kind === "approving"
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {status.kind === "approveFailed" ? (
        <div role="alert" className="flex items-start gap-2 text-sm text-intent-danger-text flex-1 min-w-0">
          <AlertTriangle aria-hidden className="size-4 mt-0.5 shrink-0" />
          <span>Approval failed: {status.message}. Your overrides are kept.</span>
        </div>
      ) : (
        <span className="text-sm text-muted flex-1 min-w-0">
          {overrideCount > 0
            ? `${pluralize(overrideCount, "override")} will be applied when you approve.`
            : "No overrides. The AI decisions will be used as they are."}
        </span>
      )}
      <Button type="button" size="lg" disabled={approving} onClick={onApprove}>
        {approving && <Spinner size="sm" />}
        {approving
          ? "Approving..."
          : status.kind === "approveFailed"
            ? "Retry approval"
            : overrideCount > 0
              ? `Approve screening (${pluralize(overrideCount, "override")})`
              : "Approve screening"}
      </Button>
    </div>
  )
}
