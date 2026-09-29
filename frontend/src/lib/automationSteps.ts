/** PRISMA automation steps (src/models/enums.py PrismaAutomationStep); labels match src/prisma/diagram.py. */
export type AutomationStep =
  | "metadata_filter"
  | "rule_prefilter"
  | "keyword_ranking"
  | "batch_preranker"
  | "unclassified"

export const AUTOMATION_STEP_ORDER: readonly AutomationStep[] = [
  "metadata_filter",
  "rule_prefilter",
  "keyword_ranking",
  "batch_preranker",
  "unclassified",
]

const AUTOMATION_STEP_LABELS: Record<AutomationStep, string> = {
  metadata_filter: "metadata filter",
  rule_prefilter: "rule-based pre-filter",
  keyword_ranking: "keyword ranking",
  batch_preranker: "low relevance score",
  unclassified: "other automated step",
}

/** Derived title/abstract value the Data tab uses for records removed by automation. */
export const REMOVED_BY_AUTOMATION = "removed_by_automation"

/** Derived title/abstract values for stored records that never reached screening (src/web/papers_query.py). */
export const DUPLICATE_RECORD = "duplicate"
export const SUPERSEDED_RECORD = "superseded"

const UNSCREENED_ORIGIN_LABELS: Record<string, string> = {
  [DUPLICATE_RECORD]: "Duplicate",
  [SUPERSEDED_RECORD]: "Superseded search result",
}

/** Label for a derived unscreened-record value, or null for ordinary decisions. */
export function unscreenedOriginLabel(value: string | null | undefined): string | null {
  return value ? (UNSCREENED_ORIGIN_LABELS[value] ?? null) : null
}

export function automationStepLabel(step: string | null | undefined): string {
  if (!step) return ""
  return AUTOMATION_STEP_LABELS[step as AutomationStep] ?? step.replace(/_/g, " ")
}

export interface AutomationBreakdownEntry {
  step: string
  label: string
  count: number
}

/** Per-step counts in pipeline order; unknown steps go last. */
export function automationBreakdown(steps: Iterable<string | null | undefined>): AutomationBreakdownEntry[] {
  const counts = new Map<string, number>()
  for (const step of steps) {
    if (step) counts.set(step, (counts.get(step) ?? 0) + 1)
  }
  const rank = (step: string) => {
    const i = AUTOMATION_STEP_ORDER.indexOf(step as AutomationStep)
    return i === -1 ? AUTOMATION_STEP_ORDER.length : i
  }
  return Array.from(counts, ([step, count]) => ({ step, label: automationStepLabel(step), count })).sort(
    (a, b) => rank(a.step) - rank(b.step) || a.step.localeCompare(b.step),
  )
}
