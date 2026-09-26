import { useState } from "react"
import { AlertTriangle } from "lucide-react"
import { toast } from "sonner"
import { Spinner, FetchError } from "@/components/ui/feedback"
import { ScreeningApprovalBar } from "@/components/screening/ScreeningApprovalBar"
import { ScreeningFiltersBar, type ScreeningFilter } from "@/components/screening/ScreeningFiltersBar"
import { ScreeningPaperList } from "@/components/screening/ScreeningPaperList"
import { ScreeningSummaryHeader } from "@/components/screening/ScreeningSummaryHeader"
import { useScreeningOverrides, useScreeningSummary } from "@/hooks/useScreeningReview"
import type { ScreeningOverride } from "@/lib/api"

interface ScreeningReviewViewProps {
  runId: string
  workflowId?: string | null
  onApproveAndResume?: (overrides: ScreeningOverride[]) => Promise<void>
}

export function ScreeningReviewView({ runId, workflowId, onApproveAndResume }: ScreeningReviewViewProps) {
  const summaryQuery = useScreeningSummary(runId)
  const { overrides, setOverride, clearOverrides } = useScreeningOverrides(workflowId || runId)
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const [approveError, setApproveError] = useState<string | null>(null)
  const [filter, setFilter] = useState<ScreeningFilter>("all")

  const handleApprove = async () => {
    if (approving || approved) return
    setApproving(true)
    setApproveError(null)
    try {
      if (onApproveAndResume) {
        await onApproveAndResume(Array.from(overrides.values()))
      }
      clearOverrides()
      setApproved(true)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setApproveError(message || "Failed to approve screening")
      toast.error(message || "Failed to approve screening", { id: "screening-approve-error" })
    } finally {
      setApproving(false)
    }
  }

  if (summaryQuery.isPending) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="md" />
      </div>
    )
  }

  if (summaryQuery.isError) {
    const err = summaryQuery.error
    return (
      <div className="py-8">
        <FetchError
          message={err instanceof Error ? err.message : String(err)}
          onRetry={() => void summaryQuery.refetch()}
        />
      </div>
    )
  }

  const summary = summaryQuery.data
  const filtered = summary.papers.filter(
    (p) => filter === "all" || p.decision === filter,
  )
  const includedCount = summary.papers.filter((p) => p.decision === "include").length
  const uncertainCount = summary.papers.filter((p) => p.decision === "uncertain").length

  return (
    <div className="space-y-4">
      <ScreeningSummaryHeader />

      <ScreeningApprovalBar
        approved={approved}
        approving={approving}
        overrideCount={overrides.size}
        onApprove={() => void handleApprove()}
      />

      {approveError && (
        <div
          role="alert"
          className="flex items-start gap-2 p-3 rounded-lg bg-intent-danger-subtle border border-intent-danger-border text-sm text-intent-danger"
        >
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            Approval failed: {approveError}. Your overrides are kept; try again.
          </span>
        </div>
      )}

      <ScreeningFiltersBar
        filter={filter}
        total={summary.total}
        includedCount={includedCount}
        uncertainCount={uncertainCount}
        onFilterChange={setFilter}
      />

      <ScreeningPaperList
        papers={filtered}
        overrides={overrides}
        onOverride={setOverride}
      />
    </div>
  )
}
