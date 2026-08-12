import { describe, expect, it } from "vitest"
import { computePhaseProgress, detectAwaitingProspero, detectAwaitingReview } from "./phaseProgress"
import { PHASE_ORDER } from "./constants"

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
    expect(progress.value).toBeGreaterThan(4 / PHASE_ORDER.length)
  })
})

describe("detectAwaitingReview", () => {
  it("detects parked status from live outputs", () => {
    expect(
      detectAwaitingReview({
        status: "awaiting_review",
        historicalStatus: "awaiting_review",
        isRunning: false,
        events: [],
      }),
    ).toBe(true)
  })

  it("detects live gate from phase events before park", () => {
    expect(
      detectAwaitingReview({
        status: "streaming",
        isRunning: true,
        events: [
          { type: "phase_start", phase: "human_review_checkpoint", description: "HITL", total: null, ts: "2026-03-12T00:00:00Z" },
        ],
      }),
    ).toBe(true)
  })
})

describe("detectAwaitingProspero", () => {
  it("detects live gate from phase events", () => {
    expect(
      detectAwaitingProspero({
        status: "streaming",
        isRunning: true,
        events: [
          { type: "phase_start", phase: "phase_1_prospero_gate", description: "PROSPERO gate", total: null, ts: "2026-03-12T00:00:00Z" },
        ],
      }),
    ).toBe(true)
  })

  it("returns false after prospero phase_done without park summary", () => {
    expect(
      detectAwaitingProspero({
        status: "streaming",
        isRunning: true,
        events: [
          { type: "phase_start", phase: "phase_1_prospero_gate", description: "PROSPERO gate", total: null, ts: "2026-03-12T00:00:00Z" },
          { type: "phase_done", phase: "phase_1_prospero_gate", summary: {}, total: 0, completed: 0, ts: "2026-03-12T00:00:01Z" },
        ],
      }),
    ).toBe(false)
  })

  it("detects parked prospero from the latest done event when still parked", () => {
    expect(
      detectAwaitingProspero({
        historicalStatus: "completed",
        status: "done",
        isRunning: false,
        events: [
          {
            type: "done",
            outputs: { status: "awaiting_prospero", workflow_id: "wf-0108" },
          },
        ],
      }),
    ).toBe(true)
  })

  it("clears prospero park when a later done event completes the run", () => {
    expect(
      detectAwaitingProspero({
        historicalStatus: "completed",
        status: "done",
        isRunning: false,
        events: [
          {
            type: "done",
            outputs: { status: "awaiting_prospero", workflow_id: "wf-0108" },
          },
          {
            type: "done",
            outputs: { status: "done", workflow_id: "wf-0108" },
          },
        ],
      }),
    ).toBe(false)
  })

  it("clears prospero park when historical status is running", () => {
    expect(
      detectAwaitingProspero({
        historicalStatus: "running",
        status: "done",
        isRunning: false,
        events: [
          {
            type: "done",
            outputs: { status: "awaiting_prospero", workflow_id: "wf-0108" },
          },
        ],
      }),
    ).toBe(false)
  })
})
