/**
 * Pure Results tab category logic (no React). Test surface for deliverables navigation.
 */
export type ResultsCategory = "manuscript" | "figures" | "quality" | "files" | "references"

export interface ResultsCategoryInputs {
  hasManuscript: boolean
  hasFiguresSection: boolean
  hasExportRunId: boolean
}

export const RESULTS_CATEGORY_ORDER: ResultsCategory[] = [
  "manuscript",
  "figures",
  "quality",
  "files",
  "references",
]

/** Category opened when submissionFocusTarget is reference-papers. */
export const SUBMISSION_FOCUS_RESULTS_CATEGORY: ResultsCategory = "files"

export function buildResultsCategoryIds(inputs: ResultsCategoryInputs): ResultsCategory[] {
  const ids: ResultsCategory[] = []
  if (inputs.hasManuscript) ids.push("manuscript")
  if (inputs.hasFiguresSection) ids.push("figures")
  if (inputs.hasExportRunId) ids.push("quality")
  ids.push("files", "references")
  return ids
}

export function defaultResultsCategory(hasManuscript: boolean): ResultsCategory {
  return hasManuscript ? "manuscript" : "files"
}

/** Keep active selection valid when available categories change (e.g. run switch). */
export function resolveActiveResultsCategory(
  active: ResultsCategory,
  available: ResultsCategory[],
): ResultsCategory {
  if (available.length === 0) return "files"
  return available.includes(active) ? active : available[0]
}

export const AUDIT_FINDINGS_ANCHOR = "audit-findings"

export function categoryForHash(hash: string | null | undefined): ResultsCategory | null {
  const id = (hash ?? "").replace(/^#/, "")
  return id === AUDIT_FINDINGS_ANCHOR ? "quality" : null
}

export interface LockedResultsState {
  heading: string
  sub: string
  cta: string
  target: "review-screening" | "activity"
}

export function lockedResultsState(awaitingReview: boolean): LockedResultsState {
  if (awaitingReview) {
    return {
      heading: "Waiting on your screening review",
      sub: "The run is paused until you confirm the screening decisions.",
      cta: "Review screening",
      target: "review-screening",
    }
  }
  return {
    heading: "Results are available once the review completes.",
    sub: "Monitor progress in the Activity tab.",
    cta: "Go to Activity",
    target: "activity",
  }
}
