import { describe, expect, it } from "vitest"
import { formatPhaseName, resolveCostOpsPreset } from "./costOpsFormatters"

describe("resolveCostOpsPreset", () => {
  it("returns empty dates for all-time range", () => {
    expect(resolveCostOpsPreset("all")).toEqual({ startDate: "", endDate: "" })
  })

  it("returns bounded dates for day presets", () => {
    const range = resolveCostOpsPreset("30d")
    expect(range.startDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(range.endDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(range.startDate <= range.endDate).toBe(true)
  })
})

describe("formatPhaseName", () => {
  it("maps known phase keys from PHASE_LABEL_MAP", () => {
    expect(formatPhaseName("phase_2_search")).toBe("Search")
    expect(formatPhaseName("phase_3_screening")).toBe("Screening")
    expect(formatPhaseName("quality_rob2")).toBe("RoB 2")
    expect(formatPhaseName("finalize")).toBe("Finalize")
  })

  it("title-cases unknown phase keys after stripping prefixes", () => {
    expect(formatPhaseName("phase_9_custom_step")).toBe("Custom Step")
    expect(formatPhaseName("quality_new_tool")).toBe("New Tool")
    expect(formatPhaseName("some_other_phase")).toBe("Some Other Phase")
  })
})
