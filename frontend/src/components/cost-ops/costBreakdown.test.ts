import { describe, expect, it } from "vitest"
import {
  bucketOther,
  buildPhaseCostRows,
  costEmptyHeading,
  costPerUnit,
  formatCompact,
  formatShare,
  lastN,
  mergePhaseAliases,
  phaseDisplayLabels,
  sortByCostDesc,
  withShare,
} from "./costBreakdown"
import { formatUsd } from "./costOpsFormatters"

describe("sortByCostDesc", () => {
  it("sorts descending without mutating input", () => {
    const rows = [{ cost_usd: 1 }, { cost_usd: 3 }, { cost_usd: 2 }]
    expect(sortByCostDesc(rows).map((r) => r.cost_usd)).toEqual([3, 2, 1])
    expect(rows.map((r) => r.cost_usd)).toEqual([1, 3, 2])
  })
})

describe("withShare / formatShare", () => {
  it("computes shares against the row sum", () => {
    const shares = withShare([{ cost_usd: 3 }, { cost_usd: 1 }]).map((s) => s.share)
    expect(shares).toEqual([0.75, 0.25])
  })

  it("returns zero shares when total is zero", () => {
    expect(withShare([{ cost_usd: 0 }])[0].share).toBe(0)
  })

  it("formats small shares as <1%", () => {
    expect(formatShare(0.341)).toBe("34%")
    expect(formatShare(0.004)).toBe("<1%")
    expect(formatShare(0)).toBe("0%")
  })
})

describe("bucketOther", () => {
  const rows = Array.from({ length: 10 }, (_, i) => ({ label: `r${i}`, calls: 1, cost_usd: 10 - i }))

  it("keeps rows unchanged when under the cap", () => {
    expect(bucketOther(rows.slice(0, 3), 8)).toEqual({ rows: rows.slice(0, 3), otherCount: 0 })
  })

  it("folds the tail into an Other row that preserves totals", () => {
    const { rows: out, otherCount } = bucketOther(rows, 8)
    expect(out).toHaveLength(8)
    expect(otherCount).toBe(3)
    const other = out[7]
    expect(other.label).toBe("Other (3)")
    expect(other.calls).toBe(3)
    expect(other.cost_usd).toBe(3 + 2 + 1)
    const sumIn = rows.reduce((a, r) => a + r.cost_usd, 0)
    const sumOut = out.reduce((a, r) => a + r.cost_usd, 0)
    expect(sumOut).toBe(sumIn)
  })
})

describe("lastN", () => {
  it("reports how many leading rows were hidden", () => {
    const { rows, hidden } = lastN([1, 2, 3, 4, 5], 3)
    expect(rows).toEqual([3, 4, 5])
    expect(hidden).toBe(2)
  })
})

describe("costPerUnit", () => {
  it("divides and scales", () => {
    expect(costPerUnit(2, 10)).toBeCloseTo(0.2)
    expect(costPerUnit(1.4, 2000, 1000)).toBeCloseTo(0.7)
  })

  it("returns null for missing or zero denominators", () => {
    expect(costPerUnit(2, 0)).toBeNull()
    expect(costPerUnit(2, null)).toBeNull()
    expect(costPerUnit(2, undefined)).toBeNull()
    expect(costPerUnit(0, 10)).toBeNull()
  })
})

describe("formatCompact", () => {
  it("compacts large numbers and keeps small ones exact", () => {
    expect(formatCompact(12_345_678)).toBe("12.3M")
    expect(formatCompact(4_200)).toBe("4.2K")
    expect(formatCompact(999)).toBe("999")
  })
})

describe("formatUsd", () => {
  it("uses two decimals at or above a dollar and up to four below", () => {
    expect(formatUsd(12.345)).toBe("$12.35")
    expect(formatUsd(0.41)).toBe("$0.41")
    expect(formatUsd(0.01234)).toBe("$0.0123")
  })
})

describe("phaseDisplayLabels", () => {
  it("uses short labels and falls back to long labels on collision", () => {
    expect(phaseDisplayLabels(["citation_chasing"]).get("citation_chasing")).toBe("Citation chasing")
    const labels = phaseDisplayLabels(["citation_chasing", "phase_3_screening_citation_chasing"])
    expect(labels.get("citation_chasing")).toBe("Citation chasing")
    expect(labels.get("phase_3_screening_citation_chasing")).toBe("Citation chasing screening")
  })

  it("disambiguates the two extraction phases", () => {
    const labels = phaseDisplayLabels(["phase_4_extraction_quality", "phase_4_extraction"])
    expect(labels.get("phase_4_extraction_quality")).not.toBe(labels.get("phase_4_extraction"))
  })
})

describe("buildPhaseCostRows", () => {
  it("returns one sorted array with shares for chart and table", () => {
    const rows = buildPhaseCostRows([
      { phase: "phase_4_extraction", calls: 2, cost_usd: 1 },
      { phase: "phase_4_extraction_quality", calls: 5, cost_usd: 3 },
    ])
    expect(rows.map((r) => r.phase)).toEqual(["phase_4_extraction_quality", "phase_4_extraction"])
    expect(rows.map((r) => r.share)).toEqual([0.75, 0.25])
    expect(rows[0].label).toBe("Extraction + quality")
    expect(rows[1].label).toBe("Extraction")
  })
})

describe("costEmptyHeading", () => {
  it("differs by run state", () => {
    const copies = new Set(["finished", "running", "not_started"].map((s) => costEmptyHeading(s as never)))
    expect(copies.size).toBe(3)
  })
})

describe("mergePhaseAliases", () => {
  it("sums cost, calls and tokens for alias ids under the canonical id", () => {
    const merged = mergePhaseAliases([
      { phase: "phase_6a2_outline", calls: 2, cost_usd: 0.25, tokens_in: 100, tokens_out: 10 },
      { phase: "phase_6_writing_outline", calls: 3, cost_usd: 0.5, tokens_in: 50, tokens_out: 5 },
      { phase: "phase_6e_concept_diagram", calls: 1, cost_usd: 0.1 },
      { phase: "phase_6e_concepts", calls: 1, cost_usd: 0.2 },
      { phase: "phase_2_search", calls: 1, cost_usd: 1 },
    ])
    expect(merged).toHaveLength(3)
    const outline = merged.find((r) => r.phase === "phase_6a2_outline")
    expect(outline).toMatchObject({ calls: 5, cost_usd: 0.75, tokens_in: 150, tokens_out: 15 })
    const concepts = merged.find((r) => r.phase === "phase_6e_concepts")
    expect(concepts?.calls).toBe(2)
    expect(concepts?.cost_usd).toBeCloseTo(0.3)
  })

  it("merges aliases before building chart rows", () => {
    const rows = buildPhaseCostRows([
      { phase: "phase_6_hyde", calls: 1, cost_usd: 1 },
      { phase: "phase_6a_hyde", calls: 1, cost_usd: 1 },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ phase: "phase_6a_hyde", calls: 2, cost_usd: 2, share: 1 })
  })
})
