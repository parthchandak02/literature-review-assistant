import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react"
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
  isHumanDecision,
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
  /** True once the gate has passed: no approve bar, overrides or decision shortcuts. */
  readOnly?: boolean
}

const NO_PAPERS: ScreenedPaper[] = []
const PAGE_SIZE = 200

function errorMessage(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : String(err)
  return message || fallback
}

const PANEL_BOTTOM_PADDING = "max(1.5rem, env(safe-area-inset-bottom))"
const APPROVAL_BAR_STYLE = {
  bottom: `calc(-1 * ${PANEL_BOTTOM_PADDING})`,
  marginBottom: `calc(-1 * ${PANEL_BOTTOM_PADDING})`,
  paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom, 0px))",
} as const

export function ScreeningReviewView({
  runId,
  workflowId,
  onApproveAndResume,
  readOnly: gatePassed = false,
}: ScreeningReviewViewProps) {
  const summaryQuery = useScreeningSummary(runId)
  const review = useScreeningReview(workflowId || runId, summaryQuery.data?.papers ?? NO_PAPERS, { readOnly: gatePassed })
  const { state, dispatch, visibleRows, visibleKeys, decide } = review
  const [status, setStatus] = useState<ApprovalStatus>({ kind: "idle" })
  // An approval started here keeps its bar (progress, retry) after the gate clears.
  const readOnly = gatePassed && status.kind === "idle"
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
    runShortcut(event)
  }

  const runShortcut = (event: {
    key: string
    target: EventTarget | null
    metaKey: boolean
    ctrlKey: boolean
    altKey: boolean
    preventDefault: () => void
  }) => {
    const command = shortcutFor(event, readOnly)
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

  const runShortcutRef = useRef(runShortcut)
  useEffect(() => {
    runShortcutRef.current = runShortcut
  })
  useEffect(() => {
    // Shortcuts also work before anything in the view has focus (focus on <body>).
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || event.target !== document.body) return
      runShortcutRef.current(event)
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [])

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
  const headerCounts = readOnly
    ? { ...review.finalCounts, overridden: review.rows.filter((r) => isHumanDecision(r.paper)).length }
    : review.finalCounts

  return (
    <div className="flex flex-col min-h-full" onKeyDown={handleKeyDown}>
      <div className="space-y-4 flex-1 pb-4">
        <ScreeningSummaryHeader
          counts={headerCounts}
          reviewedCount={review.reviewedCount}
          readOnly={readOnly}
          automation={review.automation}
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
          readOnly={readOnly}
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
          readOnly={readOnly}
        />
        {hiddenCount > 0 && (
          <div className="flex justify-center">
            <Button type="button" variant="outline" size="sm" onClick={() => setRenderLimit((n) => n + PAGE_SIZE)}>
              Show {Math.min(PAGE_SIZE, hiddenCount)} more ({hiddenCount} not shown)
            </Button>
          </div>
        )}
      </div>

      {!readOnly && (
      <div
        className="sticky z-20 -mx-6 border-t border-border bg-background px-6 pt-3"
        style={APPROVAL_BAR_STYLE}
        data-testid="screening-approval-bar"
      >
        <ScreeningApprovalBar
          status={status}
          overrideCount={review.finalCounts.overridden}
          onApprove={() => setConfirmOpen(true)}
          onRetryResume={() => void runApproval(true)}
        />
      </div>
      )}

      <ConfirmDialog
        open={confirmOpen && !locked && !readOnly}
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
