import type { ReviewTypeChoice } from "./types"

type TriState = "yes" | "no" | "unsure"

export type DecisionStep =
  | "broad"
  | "map_evidence"
  | "focused_iedo"
  | "determine_evidence"
  | "unsure_pick"

export interface DecisionAnswers {
  broad?: TriState
  mapEvidence?: TriState
  focusedIedo?: TriState
  determineEvidence?: TriState
}

export function resolveReviewType(answers: DecisionAnswers): ReviewTypeChoice | null {
  if (answers.broad === "unsure") return null

  if (answers.broad === "yes") {
    if (answers.mapEvidence === "yes") return "scoping"
    if (answers.mapEvidence === "no") return "systematic"
    return null
  }

  if (answers.broad === "no") {
    if (answers.focusedIedo === "unsure") return null
    if (answers.focusedIedo === "no") return "scoping"
    if (answers.focusedIedo === "yes") {
      if (answers.determineEvidence === "yes") return "systematic"
      if (answers.determineEvidence === "no") return "scoping"
      return null
    }
  }

  return null
}

export function nextDecisionStep(
  step: DecisionStep,
  answer: TriState,
): { step: DecisionStep; answers: Partial<DecisionAnswers> } {
  switch (step) {
    case "broad":
      if (answer === "unsure") {
        return { step: "unsure_pick", answers: { broad: answer } }
      }
      if (answer === "yes") {
        return { step: "map_evidence", answers: { broad: answer } }
      }
      return { step: "focused_iedo", answers: { broad: answer } }

    case "map_evidence":
      if (answer === "unsure") {
        return { step: "unsure_pick", answers: { mapEvidence: answer } }
      }
      return { step: "map_evidence", answers: { mapEvidence: answer } }

    case "focused_iedo":
      if (answer === "unsure") {
        return { step: "unsure_pick", answers: { focusedIedo: answer } }
      }
      if (answer === "yes") {
        return { step: "determine_evidence", answers: { focusedIedo: answer } }
      }
      return { step: "focused_iedo", answers: { focusedIedo: answer } }

    case "determine_evidence":
      if (answer === "unsure") {
        return { step: "unsure_pick", answers: { determineEvidence: answer } }
      }
      return { step: "determine_evidence", answers: { determineEvidence: answer } }

    default:
      return { step, answers: {} }
  }
}
