import type { PrismaLiveCounts, ReviewEvent } from "./api"

export type FunnelStageKind = "count" | "removed"

export interface FunnelStage {
  key: string
  label: string
  count: number
  colorClass: string
  kind?: FunnelStageKind
}

type Summary = Record<string, unknown> | null | undefined

function summaryNumber(summary: Summary, key: string): number | null {
  const value = summary?.[key]
  if (value == null) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function lastPhaseSummary(events: ReviewEvent[], phase: string): Summary {
  let summary: Summary = null
  for (const e of events) {
    if (e.type === "phase_done" && e.phase === phase) summary = e.summary as Summary
  }
  return summary
}

/**
 * Derive the screening funnel from the event stream using the PRISMA 2020
 * definitions of the backend builder (`src/prisma/diagram.py::build_prisma_counts`):
 *
 *   identified   = phase_2_search.total_records (else last success per connector)
 *   duplicates   = phase_2_search.dedup
 *   automation   = every automated exclusion before reviewer screening:
 *                  screening_prefilter_done.metadata_rejected (metadata filter)
 *                  + screening_prefilter_done.automation_excluded (rule-based pre-filter, keyword ranking)
 *                  + batch_screen_done.excluded (batch pre-ranker)
 *   screened     = records after dedup - automation (records that reached reviewer screening)
 *   sought       = phase_3_screening.fulltext_sought (else unique full-text decisions)
 *   not retrieved= phase_3_screening.fulltext_not_retrieved
 *   assessed     = phase_3_screening.fulltext_retrieved (else sought - not retrieved)
 *   included     = canonicalIncluded when known, else phase_3_screening.included
 */
export function computeFunnelStages(events: ReviewEvent[], canonicalIncluded: number | null = null): FunnelStage[] {
  const recordsByConnector = new Map<string, number>()
  for (const e of events) {
    if (e.type === "connector_result" && e.status === "success") {
      recordsByConnector.set(e.name, e.records ?? 0)
    }
  }
  let connectorTotal = 0
  for (const records of recordsByConnector.values()) connectorTotal += records

  const search = lastPhaseSummary(events, "phase_2_search")
  const screening = lastPhaseSummary(events, "phase_3_screening")
  const citation = lastPhaseSummary(events, "citation_chasing")

  const afterDedup = summaryNumber(search, "papers")
  const identified = summaryNumber(search, "total_records") ?? (connectorTotal > 0 ? connectorTotal : afterDedup)
  const duplicates =
    summaryNumber(search, "dedup") ?? (identified != null && afterDedup != null ? identified - afterDedup : null)

  let batchExcluded: number | null = null
  let prefilterExcluded: number | null = null
  for (const e of events) {
    const payload = e as unknown as Record<string, unknown>
    if (e.type === "batch_screen_done" && payload.excluded != null) {
      batchExcluded = Number(payload.excluded) || 0
    }
    if (e.type === "screening_prefilter_done") {
      prefilterExcluded = (Number(payload.metadata_rejected) || 0) + (Number(payload.automation_excluded) || 0)
    }
  }
  const screeningStarted =
    batchExcluded != null ||
    prefilterExcluded != null ||
    screening != null ||
    events.some((e) => e.type === "screening_decision")
  const automation = (prefilterExcluded ?? 0) + (batchExcluded ?? 0)
  const screened = afterDedup != null && screeningStarted ? Math.max(0, afterDedup - automation) : null

  const fulltextIds = new Set<string>()
  for (const e of events) {
    if (e.type === "screening_decision" && e.stage === "fulltext") fulltextIds.add(e.paper_id)
  }
  const sought = summaryNumber(screening, "fulltext_sought") ?? (fulltextIds.size > 0 ? fulltextIds.size : null)
  const notRetrieved = summaryNumber(screening, "fulltext_not_retrieved")
  const assessed =
    summaryNumber(screening, "fulltext_retrieved") ??
    (sought != null && notRetrieved != null ? Math.max(0, sought - notRetrieved) : null)

  let included = canonicalIncluded ?? summaryNumber(screening, "included")
  if (included == null) {
    const fulltextFinal = new Map<string, string>()
    for (const e of events) {
      if (e.type === "screening_decision" && e.stage === "fulltext") fulltextFinal.set(e.paper_id, e.decision)
    }
    const n = [...fulltextFinal.values()].filter((d) => d === "include" || d === "uncertain").length
    if (n > 0) included = n
  }

  const chased = summaryNumber(citation, "chased_included")
  return buildFunnelStages({ identified, duplicates, afterDedup, automation, screened, sought, notRetrieved, assessed, included, chased })
}

interface FunnelValues {
  identified: number | null
  duplicates: number | null
  afterDedup: number | null
  automation: number
  screened: number | null
  sought: number | null
  notRetrieved: number | null
  assessed: number | null
  included: number | null
  chased: number | null
}

function buildFunnelStages(v: FunnelValues): FunnelStage[] {
  const stages: FunnelStage[] = []
  const count = (key: string, label: string, n: number | null, colorClass: string) => {
    if (n == null || n <= 0) return
    stages.push({ key, label, count: n, colorClass, kind: "count" })
  }
  const removed = (key: string, label: string, n: number | null) => {
    if (n == null || n <= 0) return
    stages.push({ key, label, count: n, colorClass: "text-muted", kind: "removed" })
  }
  const { screened, sought, assessed, included } = v

  count("identified", "identified", v.identified, "text-intent-info")
  removed("duplicates", "duplicates removed", v.duplicates)
  if (screened == null) count("deduped", "after duplicates removed", v.afterDedup, "text-intent-info")
  removed("automation", "removed by automation", screened != null ? v.automation : null)
  count("screened", "screened", screened, "text-intent-primary")
  removed("excluded_ta", "excluded at title/abstract", screened != null && sought != null ? screened - sought : null)
  count("sought", "sought for retrieval", sought, "text-intent-active")
  removed("not_retrieved", "not retrieved", assessed != null ? v.notRetrieved : null)
  count("assessed", "assessed for eligibility", assessed, "text-intent-warning")
  removed("excluded_ft", "excluded at full text", assessed != null && included != null ? assessed - included : null)
  count("included", "included", included, "text-intent-success")
  if (v.chased != null && v.chased > 0) {
    stages.push({ key: "chased", label: "+ chased", count: v.chased, colorClass: "text-intent-info", kind: "count" })
  }
  return stages
}

/**
 * Funnel from the backend PRISMA builder (GET /api/run/{run_id}/prisma-counts) for
 * completed or non-live runs, so the popover always matches the figure.
 * `chased` comes from the event stream (citation chasing is not a PRISMA box).
 */
export function computeFunnelStagesFromPrismaCounts(counts: PrismaLiveCounts, chased: number | null = null): FunnelStage[] {
  return buildFunnelStages({
    identified: counts.total_identified_databases + counts.total_identified_other,
    duplicates: counts.duplicates_removed,
    afterDedup: counts.records_after_deduplication,
    automation: counts.automation_excluded,
    screened: counts.records_screened,
    sought: counts.reports_sought,
    notRetrieved: counts.reports_not_retrieved,
    assessed: counts.reports_assessed,
    included: counts.total_included,
    chased,
  })
}

export function chasedFromEvents(events: ReviewEvent[]): number | null {
  return summaryNumber(lastPhaseSummary(events, "citation_chasing"), "chased_included")
}
