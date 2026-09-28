import type { ReviewTypeChoice } from "./types"

export const GEN_STEPS: { key: string; label: string; shortLabel: string; detail: string }[] = [
  { key: "start", shortLabel: "Question", label: "Reading your research question", detail: "Working out scope, field, and intent" },
  { key: "web_research", shortLabel: "Web search", label: "Searching the web", detail: "Finding brand names, synonyms, and field terms" },
  { key: "web_research_fallback", shortLabel: "Fallback", label: "Web search unavailable", detail: "Using model knowledge instead of web results" },
  { key: "web_research_done", shortLabel: "Findings", label: "Summarizing web findings", detail: "Turning search results into a research brief" },
  { key: "structuring", shortLabel: "PICO", label: "Generating PICO and criteria", detail: "Keywords, inclusion/exclusion criteria, domain and scope" },
  { key: "topic_routing", shortLabel: "Database routing", label: "Choosing databases", detail: "Picking which literature databases to search for this topic" },
  { key: "finalizing", shortLabel: "Finalize", label: "Finalizing your config", detail: "Checking the config and writing it as YAML" },
]

export const WEB_RESEARCH_FALLBACK_STEP = "web_research_fallback"
export const WEB_RESEARCH_DONE_INDEX = GEN_STEPS.findIndex((s) => s.key === "web_research_done")

const STRUCTURING_BY_REVIEW_TYPE: Record<
  ReviewTypeChoice,
  { shortLabel: string; label: string; detail: string }
> = {
  systematic: {
    shortLabel: "PICO",
    label: "Generating PICO and criteria",
    detail: "Population, intervention, comparison, outcome, keywords, and screening criteria",
  },
  scoping: {
    shortLabel: "PCC",
    label: "Generating PCC and criteria",
    detail: "Population, concept, context, keywords, and screening criteria",
  },
}

export function structuringStepForReviewType(reviewType: ReviewTypeChoice): {
  shortLabel: string
  label: string
  detail: string
} {
  return STRUCTURING_BY_REVIEW_TYPE[reviewType]
}

export function genStepsForReviewType(reviewType: ReviewTypeChoice | null) {
  if (!reviewType) return GEN_STEPS
  const structuring = structuringStepForReviewType(reviewType)
  return GEN_STEPS.map((step) => (step.key === "structuring" ? { ...step, ...structuring } : step))
}
