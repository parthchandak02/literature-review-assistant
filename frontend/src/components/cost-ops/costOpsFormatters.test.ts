import { describe, expect, it } from "vitest"
import {
  formatAxisCost,
  formatUsd,
  niceCostTicks,
  formatPhaseName,
  formatSpendBucketAxisLabel,
  formatSpendBucketLabel,
  resolveCostOpsPreset,
  sqliteWeekStart,
  usdFormatterFor,
} from "./costOpsFormatters"

describe("formatUsd", () => {
  it("uses exactly 4 decimals under $1 and 2 from $1", () => {
    expect(formatUsd(0.011018)).toBe("$0.0110")
    expect(formatUsd(0.715)).toBe("$0.7150")
    expect(formatUsd(0.2008)).toBe("$0.2008")
    expect(formatUsd(1.204984)).toBe("$1.20")
    expect(formatUsd(1234.5)).toBe("$1,234.50")
  })

  it("renders zero and non-finite values as $0.00", () => {
    expect(formatUsd(0)).toBe("$0.00")
    expect(formatUsd(Number.NaN)).toBe("$0.00")
  })
})

describe("usdFormatterFor", () => {
  it("uses 4 decimals for every value when any value is below $1", () => {
    const fmt = usdFormatterFor([1.204984, 0.4097, 0])
    expect([1.204984, 0.4097, 0].map(fmt)).toEqual(["$1.2050", "$0.4097", "$0.0000"])
  })

  it("uses 2 decimals when every non-zero value is at least $1", () => {
    const fmt = usdFormatterFor([12.5, 1234.5, 0])
    expect([12.5, 1234.5, 0].map(fmt)).toEqual(["$12.50", "$1,234.50", "$0.00"])
  })
})

describe("niceCostTicks", () => {
  it("returns evenly spaced round ticks covering the max", () => {
    expect(niceCostTicks(1.205)).toEqual([0, 0.5, 1, 1.5])
    expect(niceCostTicks(1.4)).toEqual([0, 0.5, 1, 1.5])
    expect(niceCostTicks(0.042)).toEqual([0, 0.02, 0.04, 0.06])
    expect(niceCostTicks(10)).toEqual([0, 2.5, 5, 7.5, 10])
    expect(niceCostTicks(0)).toEqual([0])
  })

  it("formats axis ticks without padding zeros", () => {
    expect(niceCostTicks(1.205).map(formatAxisCost)).toEqual(["$0.00", "$0.50", "$1.00", "$1.50"])
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
  it("maps known phase keys to short phase labels", () => {
    expect(formatPhaseName("phase_2_search")).toBe("Search")
    expect(formatPhaseName("phase_3_screening")).toBe("Screening")
    expect(formatPhaseName("quality_rob2")).toBe("RoB 2")
    expect(formatPhaseName("finalize")).toBe("Finalize")
  })

  it("sentence-cases unknown phase keys after stripping prefixes", () => {
    expect(formatPhaseName("phase_9_custom_step")).toBe("Custom step")
    expect(formatPhaseName("quality_new_tool")).toBe("New tool")
    expect(formatPhaseName("some_other_phase")).toBe("Some other phase")
  })
})
