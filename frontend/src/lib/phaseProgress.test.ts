import { describe, expect, it } from "vitest"
import { computePhaseProgress } from "./phaseProgress"

describe("computePhaseProgress", () => {
  it("treats progress-only events as a running phase", () => {
    const progress = computePhaseProgress([
      { type: "phase_done", phase: "phase_2_search", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:00Z" },
      { type: "progress", phase: "phase_3_screening", current: 50, total: 100, ts: "2026-03-12T00:00:01Z" },
    ])

    expect(progress.completedPhases).toBe(1)
    expect(progress.currentPhaseFraction).toBe(0.5)
    expect(progress.value).toBeGreaterThan(0)
  })

  it("surfaces embedding phase progress instead of appearing idle", () => {
    const progress = computePhaseProgress([
      { type: "phase_done", phase: "phase_2_search", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:00Z" },
      { type: "phase_done", phase: "phase_3_screening", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:01Z" },
      { type: "phase_done", phase: "fulltext_pdf_retrieval", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:02Z" },
      { type: "phase_done", phase: "phase_4_extraction_quality", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:03Z" },
      { type: "progress", phase: "phase_4b_embedding", current: 2, total: 8, ts: "2026-03-12T00:00:04Z" },
    ])

    expect(progress.completedPhases).toBe(4)
    expect(progress.currentPhaseFraction).toBe(0.25)
    expect(progress.value).toBeGreaterThan(4 / 9)
  })
})
