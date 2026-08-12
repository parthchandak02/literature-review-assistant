import { describe, expect, it } from "vitest"
import {
  formatPhaseName,
  formatCostGroupAxisLabel,
  formatSpendBucketAxisLabel,
  formatSpendBucketLabel,
  resolveCostOpsPreset,
  sqliteWeekStart,
} from "./costOpsFormatters"

describe("formatCostGroupAxisLabel", () => {
  it("shortens workflow ids for narrow charts", () => {
    expect(formatCostGroupAxisLabel("wf-0083", "workflow")).toBe("0083")
  })

  it("uses model tail after provider prefix", () => {
    expect(formatCostGroupAxisLabel("google:gemini-2.0-flash", "model")).toBe("gemini-2.0-…")
  })

  it("abbreviates multi-word phase names", () => {
    expect(formatCostGroupAxisLabel("Pdf Vision Extraction", "phase")).toBe("Pdf Visi Extr")
  })
})

describe("formatSpendBucketLabel", () => {
  it("formats day buckets as readable dates", () => {
    expect(formatSpendBucketLabel("2026-08-12", "day")).toMatch(/Aug 12, 2026/)
    expect(formatSpendBucketAxisLabel("2026-08-12", "day")).toBe("Aug 12")
  })

  it("formats month buckets as month and year", () => {
    expect(formatSpendBucketLabel("2026-08", "month")).toBe("August 2026")
    expect(formatSpendBucketAxisLabel("2026-08", "month")).toBe("Aug")
  })

  it("formats week buckets as date ranges", () => {
    const start = sqliteWeekStart(2026, 28)
    expect(formatSpendBucketLabel("2026-W28", "week")).toContain(String(start.getDate()))
    expect(formatSpendBucketAxisLabel("2026-W28", "week")).toMatch(/Jul|Aug/)
  })
})

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
