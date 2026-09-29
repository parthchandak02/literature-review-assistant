import { ClipboardCheck } from "lucide-react"
import type { ElementType } from "react"
import type { RunTab } from "@/context/runSessionTypes"

export interface ScreeningTabItem {
  id: RunTab
  label: string
  icon: ElementType
  accent?: "violet" | "amber"
}

const REVIEW_SCREENING_TAB: ScreeningTabItem = {
  id: "review-screening",
  label: "Review Screening",
  icon: ClipboardCheck,
  accent: "amber",
}

/** Read-only screening decisions, shown once screening has finished. */
const SCREENING_READ_ONLY_TAB: ScreeningTabItem = {
  id: "review-screening",
  label: "Screening",
  icon: ClipboardCheck,
}

/** Screening tab: editable at the review gate, read-only once screening has decisions, hidden before. */
export function screeningTabFor(input: {
  isAwaitingReview: boolean
  hasScreeningDecisions: boolean
  activeTab: RunTab
}): ScreeningTabItem | null {
  if (input.isAwaitingReview) return REVIEW_SCREENING_TAB
  if (input.hasScreeningDecisions || input.activeTab === "review-screening") return SCREENING_READ_ONLY_TAB
  return null
}
