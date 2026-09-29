import { describe, expect, it } from "vitest"
import { groupPhasesByMilestone } from "./ResumeConfirmDialog"

describe("groupPhasesByMilestone", () => {
  it("shows one label when the stage and phase labels overlap", () => {
    expect(groupPhasesByMilestone(["finalize"])).toEqual([
      { key: "finalize", milestone: "Finalize and export", phases: [] },
    ])
  })

  it("keeps the phase list when the stage has several phases", () => {
    expect(groupPhasesByMilestone(["phase_7_audit", "finalize"])).toEqual([
      { key: "finalize", milestone: "Finalize", phases: ["Manuscript audit", "Finalize and export"] },
    ])
  })
})
