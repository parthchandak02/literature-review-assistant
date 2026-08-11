import { useMemo } from "react"
import type { ReviewEvent } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import type { SelectedRun } from "@/context/runSessionTypes"
import { resolveRunHeaderStatus } from "@/lib/constants"
import { detectAwaitingProspero, detectAwaitingReview } from "@/lib/phaseProgress"
import { computeFunnelStages, type FunnelStage } from "@/lib/funnelStages"

export interface RunChromeVM {
  statusLabel: string
  statusClassName: string
  displayFunnelStages: FunnelStage[]
  fallbackFound: number | null
  fallbackIncluded: number | null
  displayCost: number | null
  isRunning: boolean
  isDone: boolean
  isCancelled: boolean
  isFailed: boolean
  isAwaitingProspero: boolean
  isAwaitingReview: boolean
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

  const funnelStages = computeFunnelStages(effectiveEvents)
  const canonicalIncluded =
    (isHistorical || isDone) && run.papersIncluded != null && run.papersIncluded > 0
      ? run.papersIncluded
      : null
  const displayFunnelStages = applyCanonicalIncluded(funnelStages, canonicalIncluded)

  const fallbackFound = run.papersFound ?? null
  const fallbackIncluded = run.papersIncluded ?? null

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
    isRunning,
    isDone,
    isCancelled,
    isFailed,
    isAwaitingProspero,
    isAwaitingReview,
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
