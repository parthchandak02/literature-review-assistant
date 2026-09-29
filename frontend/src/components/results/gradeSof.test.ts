import { describe, expect, it } from "vitest"
import type { GradeSofRow } from "@/lib/api"
import { gradeRowView } from "./gradeSof"

const base: GradeSofRow = {
  outcome_name: "Cadence (motoric dual-task walking)",
  n_studies: 1,
  study_design: "rct",
  risk_of_bias: "serious",
  inconsistency: "none",
  indirectness: "not assessed*",
  imprecision: "very serious",
  other_considerations: "none",
  certainty: "low",
  effect_summary: "Downgraded one level for risk of bias.",
}

describe("gradeRowView", () => {
  it("maps backend SoF fields to display cells", () => {
    const view = gradeRowView(base, 0)
    expect(view.outcome).toBe("Cadence (motoric dual-task walking)")
    expect(view.studies).toBe("1 study · RCT")
    expect(view.downgrades).toEqual(["Risk of bias", "Imprecision (very serious)"])
    expect(view.certainty).toBe("Low")
    expect(view.certaintyVariant).toBe("warning")
    expect(view.rationale).toBe("Downgraded one level for risk of bias.")
  })

  it("returns nulls for missing fields so the row can show a partial state", () => {
    const view = gradeRowView(
      { ...base, outcome_name: "", n_studies: null, study_design: null, certainty: "", effect_summary: null },
      2,
    )
    expect(view.outcome).toBeNull()
    expect(view.studies).toBeNull()
    expect(view.certainty).toBeNull()
    expect(view.rationale).toBeNull()
    expect(view.key).toBe("2-outcome")
  })

  it("labels multi-study cross-sectional evidence and very low certainty", () => {
    const view = gradeRowView({ ...base, n_studies: 3, study_design: "cross_sectional", certainty: "very_low" }, 1)
    expect(view.studies).toBe("3 studies · Cross-sectional")
    expect(view.certainty).toBe("Very low")
    expect(view.certaintyVariant).toBe("danger")
  })

  it("explains low certainty without downgrades from the starting level", () => {
    const observational = {
      ...base,
      outcome_name: "nationally estimated pickleball-related injuries",
      study_design: "cross_sectional",
      risk_of_bias: "not serious",
      imprecision: "not serious",
      indirectness: "not serious",
    }
    const view = gradeRowView(observational, 0)
    expect(view.downgrades).toEqual([])
    expect(view.downgradeNote).toBe("Starts low (observational design)")
    expect(view.outcome).toBe("Nationally estimated pickleball-related injuries")
    expect(gradeRowView({ ...observational, starting_certainty: "low", study_design: null }, 0).downgradeNote).toBe(
      "Starts low",
    )
    expect(gradeRowView({ ...observational, study_design: "rct", certainty: "high" }, 0).downgradeNote).toBe("None")
    expect(gradeRowView(base, 0).downgradeNote).toBe("Risk of bias, Imprecision (very serious)")
  })
})
