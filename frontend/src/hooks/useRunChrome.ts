import { useMemo } from "react"
import type { PrismaLiveCounts, ReviewEvent } from "@/lib/api"
import type { CostStats } from "@/hooks/useCostStats"
import type { SelectedRun } from "@/context/runSessionTypes"
import { isNeedsRevisionStatus, resolveRunHeaderStatus, STATUS_TEXT } from "@/lib/constants"
import { CONFIG_STALLED_LABEL, isConfigGenerationStalled } from "@/lib/configGenerationStall"
import { detectAwaitingProspero, detectAwaitingReview } from "@/lib/phaseProgress"
import {
  chasedFromEvents,
  computeFunnelStages,
  computeFunnelStagesFromPrismaCounts,
  type FunnelStage,
} from "@/lib/funnelStages"
import { resolveRunGate, type RunGate } from "@/components/run/runRouting"

const SCREENING_PHASE = "phase_3_screening"

export interface RunChromeVM {
  statusLabel: string
  statusClassName: string
  displayFunnelStages: FunnelStage[]
  fallbackFound: number | null
  fallbackIncluded: number | null
  displayCost: number | null
  /** Final included count for the outcome line ("6 included of 1,715 records"). */
  outcomeIncluded: number | null
  /** PRISMA records identified (first funnel stage, else papersFound). */
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
  /** Config generation has no live stream and no update for over an hour. */
  isConfigStalled: boolean
  /** Run has screening decisions to show: parked at the review gate or screening already finished. */
  hasScreeningDecisions: boolean
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
  /** Backend PRISMA counts; used for the funnel whenever the run is not actively running. */
  prismaCounts?: PrismaLiveCounts | null
  /** True while this browser is streaming a config generation for the run. */
  configStreamActive?: boolean
  /** Clock for the stall rule; defaults to Date.now(). */
  now?: number
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
    prismaCounts = null,
    configStreamActive = false,
    now = Date.now(),
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

  const canonicalIncluded =
    (isHistorical || isDone) && run.papersIncluded != null ? run.papersIncluded : null
  const displayFunnelStages =
    !isRunning && prismaCounts != null
      ? computeFunnelStagesFromPrismaCounts(prismaCounts, chasedFromEvents(effectiveEvents))
      : computeFunnelStages(effectiveEvents, canonicalIncluded)

  const fallbackFound = run.papersFound ?? null
  const fallbackIncluded = run.papersIncluded ?? null

  const includedStage = displayFunnelStages.find((s) => s.key === "included")
  const outcomeIncluded = includedStage?.count ?? (fallbackIncluded != null && fallbackIncluded > 0 ? fallbackIncluded : null)
  const firstStage = displayFunnelStages.find((s) => s.key === "identified" || s.key === "deduped")
  const outcomeRecords = firstStage?.count ?? (fallbackFound != null && fallbackFound > 0 ? fallbackFound : null)

  const hasScreeningDecisions =
    isAwaitingReview ||
    effectiveEvents.some((e) => e.type === "phase_done" && e.phase === SCREENING_PHASE) ||
    (prismaCounts?.records_screened ?? 0) > 0

  const isConfigStalled = isConfigGenerationStalled(
    { status: run.historicalStatus, created_at: run.createdAt, updated_at: run.updatedAt },
    isViewingLiveRun || configStreamActive,
    now,
  )

  const gate = resolveRunGate({
    status,
    historicalStatus: run.historicalStatus,
    isAwaitingProspero,
    isAwaitingReview,
    isRunning,
    isConfigStalled,
  })

  const total = (run.historicalCost ?? 0) + costStats.total_cost
  const displayCost = total > 0 ? total : null

  const headerStatus = resolveRunHeaderStatus({
    status,
    isDone,
    isRunning,
    isCancelled,
    isFailed,
    isAwaitingReview,
    isAwaitingProspero,
    isNeedsRevision,
  })
  const statusLabel = isConfigStalled ? CONFIG_STALLED_LABEL : headerStatus.label
  const statusClassName = isConfigStalled ? STATUS_TEXT.stale : headerStatus.className

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
    isConfigStalled,
    hasScreeningDecisions,
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
    prismaCounts,
    configStreamActive,
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
        prismaCounts,
        configStreamActive,
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
      prismaCounts,
      configStreamActive,
    ],
  )
}
