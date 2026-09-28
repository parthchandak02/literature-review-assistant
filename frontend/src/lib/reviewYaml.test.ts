import { describe, expect, it } from "vitest"
import { reviewTypeFromYaml, validateReviewYaml } from "./reviewYaml"

describe("validateReviewYaml", () => {
  it("accepts a valid mapping", () => {
    expect(validateReviewYaml("research_question: x\nreview_type: systematic\n")).toBeNull()
  })

  it("reports the line of a syntax error", () => {
    const issue = validateReviewYaml("research_question: x\nkeywords:\n\t- a\n")
    expect(issue?.line).toBe(3)
    expect(issue?.message).toMatch(/Tabs are not allowed/)
    expect(issue?.message).not.toMatch(/at line/)
  })

  it("rejects empty and non-mapping documents", () => {
    expect(validateReviewYaml("  ")?.message).toBe("Config is empty.")
    expect(validateReviewYaml("- a\n- b\n")?.message).toMatch(/mapping/)
  })
})

describe("reviewTypeFromYaml", () => {
  it("reads the top-level review_type", () => {
    expect(reviewTypeFromYaml("review_type: scoping\n")).toBe("scoping")
    expect(reviewTypeFromYaml("review_type: 'systematic'\n")).toBe("systematic")
    expect(reviewTypeFromYaml("  review_type: scoping\n")).toBeNull()
    expect(reviewTypeFromYaml("research_question: x\n")).toBeNull()
  })
})
