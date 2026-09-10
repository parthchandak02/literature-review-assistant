import { describe, expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { ReviewTypeDecisionStage } from "./ReviewTypeDecisionStage"
import { nextDecisionStep, resolveReviewType } from "./reviewTypeDecisionLogic"

describe("resolveReviewType", () => {
  it("returns scoping for broad yes and map evidence yes", () => {
    expect(
      resolveReviewType({
        broad: "yes",
        mapEvidence: "yes",
      }),
    ).toBe("scoping")
  })

  it("returns systematic for broad yes and map evidence no", () => {
    expect(
      resolveReviewType({
        broad: "yes",
        mapEvidence: "no",
      }),
    ).toBe("systematic")
  })

  it("returns systematic for narrow focused IEDO with determine evidence yes", () => {
    expect(
      resolveReviewType({
        broad: "no",
        focusedIedo: "yes",
        determineEvidence: "yes",
      }),
    ).toBe("systematic")
  })

  it("returns scoping for narrow focused IEDO with determine evidence no", () => {
    expect(
      resolveReviewType({
        broad: "no",
        focusedIedo: "yes",
        determineEvidence: "no",
      }),
    ).toBe("scoping")
  })

  it("returns scoping for narrow non-IEDO questions", () => {
    expect(
      resolveReviewType({
        broad: "no",
        focusedIedo: "no",
      }),
    ).toBe("scoping")
  })

  it("returns null when answers are incomplete or unsure", () => {
    expect(resolveReviewType({ broad: "unsure" })).toBeNull()
    expect(resolveReviewType({ broad: "yes", mapEvidence: "unsure" })).toBeNull()
    expect(
      resolveReviewType({ broad: "no", focusedIedo: "yes", determineEvidence: "unsure" }),
    ).toBeNull()
  })
})

describe("nextDecisionStep", () => {
  it("routes broad yes to map evidence", () => {
    expect(nextDecisionStep("broad", "yes")).toEqual({
      step: "map_evidence",
      answers: { broad: "yes" },
    })
  })

  it("routes broad no to focused IEDO", () => {
    expect(nextDecisionStep("broad", "no")).toEqual({
      step: "focused_iedo",
      answers: { broad: "no" },
    })
  })

  it("routes broad unsure to guidance pick", () => {
    expect(nextDecisionStep("broad", "unsure")).toEqual({
      step: "unsure_pick",
      answers: { broad: "unsure" },
    })
  })

  it("routes focused IEDO yes to determine evidence", () => {
    expect(nextDecisionStep("focused_iedo", "yes")).toEqual({
      step: "determine_evidence",
      answers: { focusedIedo: "yes" },
    })
  })
})

describe("ReviewTypeDecisionStage", () => {
  it("renders the first decision question", () => {
    const html = renderToStaticMarkup(
      <ReviewTypeDecisionStage onComplete={() => undefined} />,
    )
    expect(html).toContain("Is your research question broad?")
    expect(html).toContain("Not sure")
  })
})
