import { describe, expect, it } from "vitest"
import { orderRunTabs } from "./runRouting"
import { screeningTabFor } from "./screeningTab"
import type { RunTab } from "@/context/runSessionTypes"

const BASE: Array<{ id: RunTab; label: string }> = [
  { id: "activity", label: "Activity" },
  { id: "results", label: "Results" },
  { id: "database", label: "Data" },
]

describe("screeningTabFor", () => {
  it("is hidden before screening", () => {
    expect(screeningTabFor({ isAwaitingReview: false, hasScreeningDecisions: false, activeTab: "activity" })).toBeNull()
  })

  it("is the editable review tab at the gate", () => {
    const tab = screeningTabFor({ isAwaitingReview: true, hasScreeningDecisions: true, activeTab: "results" })
    expect(tab?.label).toBe("Review Screening")
    expect(tab?.accent).toBe("amber")
  })

  it("stays as a read-only tab after Activity on every tab once screening has decisions", () => {
    for (const activeTab of ["activity", "results", "database"] as const) {
      const tab = screeningTabFor({ isAwaitingReview: false, hasScreeningDecisions: true, activeTab })
      expect(tab?.label).toBe("Screening")
      expect(orderRunTabs(BASE, tab ? { ...tab, label: tab.label } : null).map((t) => t.id)).toEqual([
        "activity",
        "review-screening",
        "results",
        "database",
      ])
    }
  })
})
