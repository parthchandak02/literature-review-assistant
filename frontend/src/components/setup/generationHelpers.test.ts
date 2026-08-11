import { describe, expect, it } from "vitest"
import { buildGenerationStepDetail } from "./generationHelpers"

describe("buildGenerationStepDetail", () => {
  it("prefers live backend detail for the active step", () => {
    expect(
      buildGenerationStepDetail(
        "web_research",
        "active",
        { detail: "Searching: drone delivery rural" },
        "Discovering brand names",
      ),
    ).toBe("Searching: drone delivery rural")
  })

  it("falls back to the default detail when no live update exists", () => {
    expect(
      buildGenerationStepDetail(
        "structuring",
        "active",
        {},
        "Generating PICO and criteria",
      ),
    ).toBe("Generating PICO and criteria")
  })

  it("describes skipped fallback steps", () => {
    expect(
      buildGenerationStepDetail(
        "web_research_fallback",
        "skipped",
        {},
        "Falling back",
      ),
    ).toBe("Skipped because web research succeeded.")
  })
})
