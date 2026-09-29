import { describe, expect, it } from "vitest"
import type { PapersFacets, PrismaLiveCounts } from "@/lib/api/db"
import { storedRecordsReconciliation } from "./storedRecords"

function facets(ta: Array<{ value: string | null; count: number }>): PapersFacets {
  return {
    years: [],
    sources: [],
    countries: [],
    ta_decisions: [],
    ft_decisions: [],
    primary_statuses: [],
    counts: { ta_decision: ta },
  }
}

const prisma = { total_identified_databases: 1715, total_identified_other: 0 } as PrismaLiveCounts

describe("storedRecordsReconciliation", () => {
  it("states how stored records reconcile with PRISMA identified", () => {
    const text = storedRecordsReconciliation(
      1716,
      facets([
        { value: "duplicate", count: 167 },
        { value: "superseded", count: 1 },
      ]),
      prisma,
    )
    expect(text).toMatch(/^1,716 stored records = 1,715 identified in PRISMA \+ 1 superseded search result\./)
    expect(text).toContain("include 167 duplicates removed before screening")
  })

  it("names unmatched extra records when they cannot be classified", () => {
    const text = storedRecordsReconciliation(1716, facets([{ value: null, count: 1 }]), prisma)
    expect(text).toMatch(/^1,716 stored records = 1,715 identified in PRISMA \+ 1 record PRISMA does not count\./)
    expect(text).toContain("show as Not screened")
  })

  it("returns null without PRISMA counts", () => {
    expect(storedRecordsReconciliation(10, facets([]), null)).toBeNull()
  })
})
