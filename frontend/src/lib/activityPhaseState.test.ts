import { describe, expect, it } from "vitest"
import {
  buildPhaseStates,
  isPhaseEligibleForResume,
  isPhaseResumeSelectable,
} from "./activityPhaseState"

describe("buildPhaseStates", () => {
  it("marks phases running on phase_start and done on phase_done", () => {
    const states = buildPhaseStates(
      [
        { type: "phase_start", phase: "phase_2_search", description: "Search", total: null, ts: "2026-03-12T00:00:00Z" },
        { type: "phase_done", phase: "phase_2_search", summary: {}, total: 10, completed: 10, ts: "2026-03-12T00:01:00Z" },
      ],
      false,
    )

    expect(states.phase_2_search).toEqual({
      status: "done",
      startedTs: "2026-03-12T00:00:00Z",
      doneTss: "2026-03-12T00:01:00Z",
      progress: { current: 10, total: 10 },
    })
  })

  it("treats progress-only events as running", () => {
    const states = buildPhaseStates(
      [
        { type: "progress", phase: "phase_3_screening", current: 5, total: 20, ts: "2026-03-12T00:00:00Z" },
      ],
      false,
    )

    expect(states.phase_3_screening).toEqual({
      status: "running",
      progress: { current: 5, total: 20 },
    })
  })

  it("coerces running phases to done when workflow is completed", () => {
    const states = buildPhaseStates(
      [
        { type: "phase_start", phase: "phase_6_writing", description: "Writing", total: null, ts: "2026-03-12T00:00:00Z" },
      ],
      true,
    )

    expect(states.phase_6_writing?.status).toBe("done")
    expect(states.phase_6_writing?.doneTss).toBe("2026-03-12T00:00:00Z")
  })
})

describe("isPhaseEligibleForResume", () => {
  const doneSearch = buildPhaseStates(
    [
      { type: "phase_done", phase: "phase_1_prospero_gate", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:00Z" },
      { type: "phase_done", phase: "phase_2_search", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:01Z" },
    ],
    false,
  )

  it("requires prerequisite phases to be done", () => {
    expect(isPhaseEligibleForResume("phase_2_search", doneSearch, false)).toBe(true)
    expect(isPhaseEligibleForResume("phase_3_screening", doneSearch, false)).toBe(false)
  })

  it("allows any done resumable phase when workflow completed", () => {
    const completedStates = buildPhaseStates(
      [
        { type: "phase_done", phase: "phase_1_prospero_gate", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:00Z" },
        { type: "phase_done", phase: "phase_2_search", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:01Z" },
        { type: "phase_done", phase: "phase_3_screening", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:02Z" },
      ],
      true,
    )

    expect(isPhaseEligibleForResume("phase_3_screening", completedStates, true)).toBe(true)
    expect(isPhaseEligibleForResume("phase_2_search", completedStates, true)).toBe(true)
  })
})

describe("isPhaseResumeSelectable", () => {
  it("matches isPhaseEligibleForResume", () => {
    const states = buildPhaseStates(
      [
        { type: "phase_done", phase: "phase_1_prospero_gate", summary: {}, total: 1, completed: 1, ts: "2026-03-12T00:00:00Z" },
      ],
      false,
    )

    expect(isPhaseResumeSelectable("phase_2_search", states, false)).toBe(
      isPhaseEligibleForResume("phase_2_search", states, false),
    )
  })
})
