import { decodeHtmlEntities, humanizeSnake } from "@/lib/humanize"
import type { ScreenedPaper, ScreeningOverride, ScreeningThresholds } from "@/lib/api"

export type AiDecision = ScreenedPaper["decision"]
export type HumanDecision = ScreeningOverride["decision"]
export type ScreeningFilter = "all" | "include" | "exclude" | "uncertain" | "overridden"
export type ScreeningSort = "confidence-asc" | "confidence-desc" | "title"
export type OverrideMap = ReadonlyMap<string, ScreeningOverride>

export const SCREENING_FILTERS: readonly ScreeningFilter[] = [
  "all",
  "include",
  "exclude",
  "uncertain",
  "overridden",
]

export const SCREENING_FILTER_LABELS: Record<ScreeningFilter, string> = {
  all: "All",
  include: "Include",
  exclude: "Exclude",
  uncertain: "Uncertain",
  overridden: "Overridden",
}

export const SCREENING_SORT_LABELS: Record<ScreeningSort, string> = {
  "confidence-asc": "Confidence: lowest first",
  "confidence-desc": "Confidence: highest first",
  title: "Title (A-Z)",
}

export interface ScreeningRowData {
  key: string
  paper: ScreenedPaper
  title: string
  authors: string
  abstract: string
  reason: string
}

export function screeningRowDomId(key: string): string {
  return `screening-row-${key.replace(/[^A-Za-z0-9_-]/g, "_")}`
}

/** The summary returns one row per paper; a repeated paper_id keeps its first row. */
export function buildRows(papers: readonly ScreenedPaper[]): ScreeningRowData[] {
  const seen = new Set<string>()
  const rows: ScreeningRowData[] = []
  for (const raw of papers) {
    if (seen.has(raw.paper_id)) continue
    seen.add(raw.paper_id)
    const paper = raw.final_decision && raw.final_decision !== raw.decision ? { ...raw, decision: raw.final_decision } : raw
    rows.push({
      key: paper.paper_id,
      paper,
      title: decodeHtmlEntities(paper.title).trim(),
      authors: decodeHtmlEntities(paper.authors).trim(),
      abstract: decodeHtmlEntities(paper.abstract).trim(),
      reason: decodeHtmlEntities(paper.reason).trim(),
    })
  }
  return rows
}

const DECIDED_BY_LABELS: Record<string, string> = {
  human_override: "Human override",
  adjudicator: "AI adjudicator",
  screening_adjudicator: "AI adjudicator",
  reviewer_a: "AI reviewer A",
  screening_reviewer_a: "AI reviewer A",
  reviewer_b: "AI reviewer B",
  screening_reviewer_b: "AI reviewer B",
}

export function humanizeDecidedBy(value: string | null | undefined): string {
  if (!value) return ""
  const key = value.trim().toLowerCase()
  return DECIDED_BY_LABELS[key] ?? humanizeSnake(key)
}

/** Codes like `wrong_population` are humanised; free-text reasons are shown as written. */
export function humanizeExclusionReason(value: string | null | undefined): string {
  const text = decodeHtmlEntities(value).trim()
  return /^[a-z0-9_]+$/.test(text) ? humanizeSnake(text) : text
}

export function isHumanDecision(paper: ScreenedPaper): boolean {
  return paper.decided_by === "human_override"
}

const pct = (value: number) => `${Math.round(value * 100)}%`

/** Plain-language meaning of the screening thresholds (see src/screening/dual_screener.py fast path). */
export function thresholdsText(thresholds: ScreeningThresholds | null | undefined): string | null {
  if (!thresholds) return null
  const origin = thresholds.source === "calibration" ? "Calibrated on this run" : "From settings"
  return (
    `${origin}: at title and abstract, the first AI reviewer's call stands when it is at least ` +
    `${pct(thresholds.include)} confident to include or ${pct(thresholds.exclude)} confident to exclude. ` +
    "Anything less certain gets a second reviewer. Full text is always double-reviewed."
  )
}

export function effectiveDecision(ai: AiDecision, override: ScreeningOverride | null | undefined): AiDecision {
  return override ? override.decision : ai
}

export interface DecisionCounts {
  total: number
  include: number
  exclude: number
  uncertain: number
  overridden: number
}

/** Counts of the decisions that will be sent on approval (AI decision unless overridden). */
export function countFinalDecisions(rows: readonly ScreeningRowData[], overrides: OverrideMap): DecisionCounts {
  const counts: DecisionCounts = { total: rows.length, include: 0, exclude: 0, uncertain: 0, overridden: 0 }
  for (const row of rows) {
    const override = overrides.get(row.key)
    counts[effectiveDecision(row.paper.decision, override)] += 1
    if (override) counts.overridden += 1
  }
  return counts
}

/** Tab counts. Decision tabs match the AI decision so rows stay put while you triage. */
export function countFilterTabs(
  rows: readonly ScreeningRowData[],
  overrides: OverrideMap,
): Record<ScreeningFilter, number> {
  const counts: Record<ScreeningFilter, number> = {
    all: rows.length,
    include: 0,
    exclude: 0,
    uncertain: 0,
    overridden: 0,
  }
  for (const row of rows) {
    counts[row.paper.decision] += 1
    if (overrides.has(row.key)) counts.overridden += 1
  }
  return counts
}

export function matchesFilter(row: ScreeningRowData, filter: ScreeningFilter, overrides: OverrideMap): boolean {
  if (filter === "all") return true
  if (filter === "overridden") return overrides.has(row.key)
  return row.paper.decision === filter
}

export function matchesSearch(row: ScreeningRowData, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return row.title.toLowerCase().includes(needle) || row.authors.toLowerCase().includes(needle)
}

const titleCollator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true })

export function compareRows(sort: ScreeningSort): (a: ScreeningRowData, b: ScreeningRowData) => number {
  if (sort === "title") return (a, b) => titleCollator.compare(a.title, b.title)
  const direction = sort === "confidence-asc" ? 1 : -1
  return (a, b) => {
    const ca = a.paper.confidence
    const cb = b.paper.confidence
    if (ca == null && cb == null) return titleCollator.compare(a.title, b.title)
    // Unscored rows are mostly rule-based excludes; keep them after the scored borderline cases.
    if (ca == null) return 1
    if (cb == null) return -1
    return (ca - cb) * direction || titleCollator.compare(a.title, b.title)
  }
}

export interface VisibleRowsQuery {
  filter: ScreeningFilter
  search: string
  sort: ScreeningSort
  /** Overrides captured when the filter last changed, so a decision doesn't yank the row away. */
  filterBasis: OverrideMap
}

export function selectVisibleRows(
  rows: readonly ScreeningRowData[],
  { filter, search, sort, filterBasis }: VisibleRowsQuery,
): ScreeningRowData[] {
  return rows
    .filter((row) => matchesFilter(row, filter, filterBasis) && matchesSearch(row, search))
    .sort(compareRows(sort))
}

/** Plain-language outcome for Uncertain papers. Source: screening_runner.py and repos/screening.py. */
export const UNCERTAIN_OUTCOME = "kept in and sent to extraction with the included papers"

export function pluralize(n: number, singular: string, plural = `${singular}s`): string {
  return `${n} ${n === 1 ? singular : plural}`
}

export function approvalSummaryText(counts: DecisionCounts): string {
  const overrides =
    counts.overridden === 0
      ? "no overrides"
      : `${pluralize(counts.overridden, "override")} will be applied`
  return (
    `${counts.include} included, ${counts.uncertain} uncertain → ${UNCERTAIN_OUTCOME}, ` +
    `${counts.exclude} excluded, ${overrides}. Extraction will start and incur model cost.`
  )
}

export function summaryLine(counts: DecisionCounts): string {
  return [
    pluralize(counts.total, "paper"),
    `${counts.include} include`,
    `${counts.exclude} exclude`,
    `${counts.uncertain} uncertain`,
    `${counts.overridden} overridden`,
  ].join(" · ")
}
