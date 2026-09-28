import { useMemo } from "react"
import type { ReviewEvent } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import type { SelectedRun } from "@/context/runSessionTypes"
import { isNeedsRevisionStatus, resolveRunHeaderStatus } from "@/lib/constants"
import { detectAwaitingProspero, detectAwaitingReview } from "@/lib/phaseProgress"
import { computeFunnelStages, type FunnelStage } from "@/lib/funnelStages"
import { resolveRunGate, type RunGate } from "@/components/run/runRouting"

export interface RunChromeVM {
  statusLabel: string
  statusClassName: string
  displayFunnelStages: FunnelStage[]
  fallbackFound: number | null
  fallbackIncluded: number | null
  displayCost: number | null
  /** Final included count for the outcome line ("6 included of 1,716 records"). */
  outcomeIncluded: number | null
  /** Records retrieved (first funnel stage, else papersFound). */
  outcomeRecords: number | null
  /** Human gate the run is parked on, if any. */
  gate: RunGate | null
  isRunning: boolean
  isDone: boolean
  isCancelled: boolean
  isFailed: boolean
  isAwaitingProspero: boolean
  isAwaitingReview: boolean
  isNeedsRevision: boolean
  isParkedGate: boolean
  liveStatus: string
}

export interface RunChromeInput {
  run: SelectedRun
  events: ReviewEvent[]
  effectiveEvents: ReviewEvent[]
  isViewingLiveRun: boolean
  /** Effective status for header/display (liveStatus when live). */
  status: string
  costStats: CostStats
  liveOutputs?: Record<string, unknown>
  prosperoPrepareInProgress?: boolean
  /** Raw SSE stream status; used for liveStatus derivation in App. Defaults to `status`. */
  streamStatus?: string
  /** Historical canonical status when not viewing live run. */
  resolvedHistoricalStatus?: string
}

function applyCanonicalIncluded(
  funnelStages: FunnelStage[],
  canonicalIncluded: number | null,
): FunnelStage[] {
  if (funnelStages.length === 0) return funnelStages
  if (canonicalIncluded == null) return funnelStages
  const next = [...funnelStages]
  const includedIdx = next.findIndex((s) => s.key === "included")
  if (includedIdx >= 0) {
    next[includedIdx] = {
      ...next[includedIdx],
      count: canonicalIncluded,
    }
    return next
  }
  next.push({
    key: "included",
    label: "included",
    count: canonicalIncluded,
    colorClass: "text-intent-success",
  })
  return next
}

/** Pure derivation for run toolbar / info-strip display state. */
export function computeRunChrome(input: RunChromeInput): RunChromeVM {
  const {
    run,
    events,
    effectiveEvents,
    isViewingLiveRun,
    status,
    costStats,
    liveOutputs = {},
    prosperoPrepareInProgress = false,
    streamStatus = status,
    resolvedHistoricalStatus,
  } = input

  const isHistorical = !isViewingLiveRun
  const rawIsRunning = status === "streaming" || status === "connecting"

  const isAwaitingProspero = detectAwaitingProspero({
    historicalStatus: run.historicalStatus,
    status,
    events: effectiveEvents,
    isRunning: rawIsRunning,
    prosperoPrepareInProgress,
  })
  const isAwaitingReview = detectAwaitingReview({
    historicalStatus: run.historicalStatus,
    status: String(liveOutputs?.status ?? status),
    events: effectiveEvents,
    isRunning: rawIsRunning,
  })
  const isParkedGate = isAwaitingProspero || isAwaitingReview

  const isDone = !isParkedGate && (run.isDone || status === "done")
  const isRunning = !isParkedGate && (status === "streaming" || status === "connecting")

  const isCancelled =
    ["cancelled", "interrupted"].includes((run.historicalStatus ?? "").toLowerCase()) ||
    status === "cancelled"
  const isFailed =
    ["failed", "error"].includes((run.historicalStatus ?? "").toLowerCase()) ||
    status === "error"

  const isNeedsRevision =
    !isRunning &&
    !isParkedGate &&
    (isNeedsRevisionStatus(run.historicalStatus) || isNeedsRevisionStatus(String(liveOutputs?.status ?? "")))

  const funnelStages = computeFunnelStages(effectiveEvents)
  const canonicalIncluded =
    (isHistorical || isDone) && run.papersIncluded != null ? run.papersIncluded : null
  const displayFunnelStages = applyCanonicalIncluded(funnelStages, canonicalIncluded)

  const fallbackFound = run.papersFound ?? null
  const fallbackIncluded = run.papersIncluded ?? null

  const includedStage = displayFunnelStages.find((s) => s.key === "included")
  const outcomeIncluded = includedStage?.count ?? (fallbackIncluded != null && fallbackIncluded > 0 ? fallbackIncluded : null)
  const firstStage = displayFunnelStages.find((s) => s.key === "raw" || s.key === "deduped")
  const outcomeRecords = firstStage?.count ?? (fallbackFound != null && fallbackFound > 0 ? fallbackFound : null)

  const gate = resolveRunGate({
    status,
    historicalStatus: run.historicalStatus,
    isAwaitingProspero,
    isAwaitingReview,
    isRunning,
  })

  const total = (run.historicalCost ?? 0) + costStats.total_cost
  const displayCost = total > 0 ? total : null

  const { label: statusLabel, className: statusClassName } = resolveRunHeaderStatus({
    status,
    isDone,
    isRunning,
    isCancelled,
    isFailed,
    isAwaitingReview,
    isAwaitingProspero,
    isNeedsRevision,
  })

  let liveStatus: string
  if (!isViewingLiveRun) {
    liveStatus = resolvedHistoricalStatus ?? status
  } else {
    const liveAwaitingProspero = detectAwaitingProspero({
      status: streamStatus,
      events,
      isRunning: true,
      prosperoPrepareInProgress,
    })
    const liveAwaitingReview = detectAwaitingReview({
      historicalStatus: run.historicalStatus,
      status: String(liveOutputs?.status ?? streamStatus),
      events,
      isRunning: true,
    })
    liveStatus = liveAwaitingProspero
      ? "awaiting_prospero"
      : liveAwaitingReview
        ? "awaiting_review"
        : streamStatus
  }

  return {
    statusLabel,
    statusClassName,
    displayFunnelStages,
    fallbackFound,
    fallbackIncluded,
    displayCost,
    outcomeIncluded,
    outcomeRecords,
    gate,
    isRunning,
    isDone,
    isCancelled,
    isFailed,
    isAwaitingProspero,
    isAwaitingReview,
    isNeedsRevision,
    isParkedGate,
    liveStatus,
  }
}

export function useRunChrome(input: RunChromeInput): RunChromeVM {
  const {
    run,
    events,
    effectiveEvents,
    isViewingLiveRun,
    status,
    costStats,
    liveOutputs,
    prosperoPrepareInProgress,
    streamStatus,
    resolvedHistoricalStatus,
  } = input

  return useMemo(
    () =>
      computeRunChrome({
        run,
        events,
        effectiveEvents,
        isViewingLiveRun,
        status,
        costStats,
        liveOutputs,
        prosperoPrepareInProgress,
        streamStatus,
        resolvedHistoricalStatus,
      }),
    [
      run,
      events,
      effectiveEvents,
      isViewingLiveRun,
      status,
      costStats,
      liveOutputs,
      prosperoPrepareInProgress,
      streamStatus,
      resolvedHistoricalStatus,
    ],
  )
}
