import { useCallback, useState, type KeyboardEvent } from "react"
import { flushSync } from "react-dom"
import { toast } from "sonner"
import { ConfirmDialog } from "@/components/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { Spinner, FetchError } from "@/components/ui/feedback"
import { ScreeningApprovalBar, type ApprovalStatus } from "@/components/screening/ScreeningApprovalBar"
import { ScreeningFiltersBar } from "@/components/screening/ScreeningFiltersBar"
import { ScreeningPaperList } from "@/components/screening/ScreeningPaperList"
import { ScreeningSummaryHeader } from "@/components/screening/ScreeningSummaryHeader"
import { shortcutFor } from "@/components/screening/screeningKeyboard"
import {
  approvalSummaryText,
  screeningRowDomId,
  type HumanDecision,
} from "@/components/screening/screeningModel"
import { isScreeningResumeError } from "@/hooks/runSession/useRunGateActions"
import { moveFocus, useScreeningReview, useScreeningSummary } from "@/hooks/useScreeningReview"
import type { ScreenedPaper, ScreeningOverride } from "@/lib/api"

interface ScreeningReviewViewProps {
  runId: string
  workflowId?: string | null
  onApproveAndResume?: (overrides: ScreeningOverride[]) => Promise<void>
}

const NO_PAPERS: ScreenedPaper[] = []
const PAGE_SIZE = 200

function errorMessage(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : String(err)
  return message || fallback
}

export function ScreeningReviewView({ runId, workflowId, onApproveAndResume }: ScreeningReviewViewProps) {
  const summaryQuery = useScreeningSummary(runId)
  const review = useScreeningReview(workflowId || runId, summaryQuery.data?.papers ?? NO_PAPERS)
  const { state, dispatch, visibleRows, visibleKeys, decide } = review
  const [status, setStatus] = useState<ApprovalStatus>({ kind: "idle" })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [renderLimit, setRenderLimit] = useState(PAGE_SIZE)

  const runApproval = useCallback(
    async (resumeOnly: boolean) => {
      setStatus({ kind: resumeOnly ? "resuming" : "approving" })
      try {
        await onApproveAndResume?.(review.overrideList)
        dispatch({ type: "resetOverrides" })
        setStatus({ kind: "done" })
      } catch (err) {
        if (isScreeningResumeError(err)) {
          dispatch({ type: "resetOverrides" })
          const message = errorMessage(err, "The run didn't resume")
          setStatus({ kind: "resumeFailed", message })
          toast.error(`Screening approved, but the run didn't resume: ${message}`, { id: "screening-approve-error" })
        } else {
          const message = errorMessage(err, "Failed to approve screening")
          setStatus({ kind: "approveFailed", message })
          toast.error(message, { id: "screening-approve-error" })
        }
      }
    },
    [dispatch, onApproveAndResume, review.overrideList],
  )

  const onDecide = useCallback((key: string, decision: HumanDecision) => decide([key], decision), [decide])
  const onClearOverride = useCallback((key: string) => dispatch({ type: "clearOverrides", keys: [key] }), [dispatch])
  const onReasonChange = useCallback(
    (key: string, reason: string) => dispatch({ type: "setReason", key, reason }),
    [dispatch],
  )
  const onToggleExpanded = useCallback((key: string) => dispatch({ type: "toggleExpanded", key }), [dispatch])
  const onToggleSelected = useCallback((key: string) => dispatch({ type: "toggleSelected", key }), [dispatch])
  const onFocusRow = useCallback((key: string) => dispatch({ type: "focus", key }), [dispatch])

  const focusedVisibleKey =
    state.focusedKey && visibleKeys.includes(state.focusedKey) ? state.focusedKey : null

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.defaultPrevented) return
    // Ignore keys from portaled menus and dialogs; React still bubbles them here.
    if (!(event.target instanceof Node) || !event.currentTarget.contains(event.target)) return
    const command = shortcutFor(event)
    if (!command) return
    if (command.type === "help") {
      event.preventDefault()
      setHelpOpen(true)
      return
    }
    if (command.type === "undo") {
      event.preventDefault()
      dispatch({ type: "undo" })
      return
    }
    if (command.type === "move") {
      event.preventDefault()
      const next = moveFocus(visibleKeys, focusedVisibleKey, command.delta)
      if (next) {
        const index = visibleKeys.indexOf(next)
        if (index >= renderLimit) flushSync(() => setRenderLimit(index + PAGE_SIZE))
        dispatch({ type: "focus", key: next })
        document.getElementById(screeningRowDomId(next))?.focus()
      }
      return
    }
    const key = focusedVisibleKey
    if (!key) return
    event.preventDefault()
    if (command.type === "decide") decide([key], command.decision)
    else if (command.type === "expand") dispatch({ type: "toggleExpanded", key })
    else dispatch({ type: "toggleSelected", key })
  }

  if (summaryQuery.isPending) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="md" />
      </div>
    )
  }

  if (summaryQuery.isError) {
    return (
      <div className="py-8">
        <FetchError
          message={errorMessage(summaryQuery.error, "Failed to load screening decisions")}
          onRetry={() => void summaryQuery.refetch()}
        />
      </div>
    )
  }

  const selectedVisibleCount = visibleKeys.reduce((n, k) => n + (state.selected.has(k) ? 1 : 0), 0)
  const selectedKeys = Array.from(state.selected)
  const renderedRows = visibleRows.length > renderLimit ? visibleRows.slice(0, renderLimit) : visibleRows
  const hiddenCount = visibleRows.length - renderedRows.length
  const locked = status.kind !== "idle" && status.kind !== "approveFailed"

  return (
    <div className="flex flex-col min-h-full" onKeyDown={handleKeyDown}>
      <div className="space-y-4 flex-1 pb-4">
        <ScreeningSummaryHeader
          counts={review.finalCounts}
          reviewedCount={review.reviewedCount}
          thresholds={summaryQuery.data.thresholds}
        />

        <ScreeningFiltersBar
          filter={state.filter}
          counts={review.tabCounts}
          search={state.search}
          sort={state.sort}
          visibleCount={visibleKeys.length}
          selectedVisibleCount={selectedVisibleCount}
          selectedCount={state.selected.size}
          canUndo={state.undoStack.length > 0}
          helpOpen={helpOpen}
          onFilterChange={(filter) => {
            setRenderLimit(PAGE_SIZE)
            dispatch({ type: "setFilter", filter })
          }}
          onSearchChange={(search) => {
            setRenderLimit(PAGE_SIZE)
            dispatch({ type: "setSearch", search })
          }}
          onSortChange={(sort) => {
            setRenderLimit(PAGE_SIZE)
            dispatch({ type: "setSort", sort })
          }}
          onSelectAllVisible={(selected) => dispatch({ type: "setSelected", keys: visibleKeys, selected })}
          onBulkDecide={(decision) => decide(selectedKeys, decision)}
          onBulkClear={() => dispatch({ type: "clearOverrides", keys: selectedKeys })}
          onUndo={() => dispatch({ type: "undo" })}
          onHelpOpenChange={setHelpOpen}
        />

        <ScreeningPaperList
          rows={renderedRows}
          overrides={state.overrides}
          focusedKey={focusedVisibleKey}
          expanded={state.expanded}
          selected={state.selected}
          onDecide={onDecide}
          onClearOverride={onClearOverride}
          onReasonChange={onReasonChange}
          onToggleExpanded={onToggleExpanded}
          onToggleSelected={onToggleSelected}
          onFocusRow={onFocusRow}
        />
        {hiddenCount > 0 && (
          <div className="flex justify-center">
            <Button type="button" variant="outline" size="sm" onClick={() => setRenderLimit((n) => n + PAGE_SIZE)}>
              Show {Math.min(PAGE_SIZE, hiddenCount)} more ({hiddenCount} not shown)
            </Button>
          </div>
        )}
      </div>

      <div className="sticky bottom-0 z-10 -mx-1 px-4 py-3 glass-toolbar border-t border-border rounded-panel">
        <ScreeningApprovalBar
          status={status}
          overrideCount={review.finalCounts.overridden}
          onApprove={() => setConfirmOpen(true)}
          onRetryResume={() => void runApproval(true)}
        />
      </div>

      <ConfirmDialog
        open={confirmOpen && !locked}
        onOpenChange={setConfirmOpen}
        title="Approve screening and start extraction?"
        description={approvalSummaryText(review.finalCounts)}
        confirmLabel="Approve and start extraction"
        pendingLabel="Approving..."
        confirmVariant="default"
        onConfirm={async () => {
          setConfirmOpen(false)
          await runApproval(false)
        }}
      />
    </div>
  )
}
