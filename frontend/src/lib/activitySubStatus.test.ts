import { describe, expect, it } from "vitest"
import {
  activeSubStatus,
  applyFailure,
  currentPhaseId,
  failureSummary,
  formatElapsed,
  formatSubStatus,
  latestResumablePhase,
  phasesRerunFrom,
  priorCostForPhases,
  resumeOptions,
  timelinePhaseFor,
  type PhaseState,
} from "./activityPhaseState"
import type { ReviewEvent } from "@/lib/api"

const NOW = Date.parse("2026-03-12T00:06:30Z")

describe("formatElapsed", () => {
  it("formats seconds, minutes and hours compactly", () => {
    expect(formatElapsed(45_000)).toBe("45s")
    expect(formatElapsed(6 * 60_000 + 30_000)).toBe("6m")
    expect(formatElapsed(72 * 60_000)).toBe("1h 12m")
    expect(formatElapsed(120 * 60_000)).toBe("2h")
    expect(formatElapsed(-5)).toBe("0s")
  })
})

describe("activeSubStatus", () => {
  it("returns null when nothing is running", () => {
    expect(activeSubStatus({}, NOW)).toBeNull()
    expect(activeSubStatus({ phase_2_search: { status: "done" } }, NOW)).toBeNull()
  })

  it("reports label, progress and elapsed for the running phase", () => {
    const states: Record<string, PhaseState> = {
      phase_2_search: { status: "done", startedTs: "2026-03-12T00:00:00Z" },
      fulltext_pdf_retrieval: {
        status: "running",
        startedTs: "2026-03-12T00:00:00Z",
        progress: { current: 34, total: 120 },
      },
    }
    const sub = activeSubStatus(states, NOW)
    expect(sub).toMatchObject({
      phase: "fulltext_pdf_retrieval",
      milestone: "discovery",
      label: "PDF retrieval",
      progressText: "34/120",
      elapsedText: "6m",
      awaiting: false,
    })
    expect(formatSubStatus(sub!)).toBe("PDF retrieval · 34/120 · 6m")
  })

  it("prefers the most recently started running phase (sub-phase over parent)", () => {
    const states: Record<string, PhaseState> = {
      phase_6_writing: { status: "running", startedTs: "2026-03-12T00:00:00Z" },
      phase_6b_phase_a: { status: "running", startedTs: "2026-03-12 00:05:00" },
    }
    const sub = activeSubStatus(states, NOW)
    expect(sub?.phase).toBe("phase_6b_phase_a")
    expect(sub?.milestone).toBe("manuscript")
    expect(sub?.elapsedText).toBe("1m")
    expect(sub?.progressText).toBeNull()
  })

  it("prefers an awaiting gate and omits elapsed time", () => {
    const states: Record<string, PhaseState> = {
      phase_2_search: { status: "running", startedTs: "2026-03-12T00:05:00Z" },
      phase_3_screening: {
        status: "awaiting",
        gateStatus: "awaiting_review",
        startedTs: "2026-03-12T00:00:00Z",
        progress: { current: 212, total: 480 },
      },
    }
    const sub = activeSubStatus(states, NOW)
    expect(sub).toMatchObject({ phase: "phase_3_screening", awaiting: true, elapsedText: null })
    expect(formatSubStatus(sub!)).toBe("Screening · 212/480")
  })

  it("formats large counts and ignores zero totals", () => {
    const big = activeSubStatus(
      { phase_3_screening: { status: "running", progress: { current: 1716, total: 2000 } } },
      NOW,
    )
    expect(big?.progressText).toBe("1,716/2,000")
    expect(big?.elapsedText).toBeNull()
    const zero = activeSubStatus(
      { phase_3_screening: { status: "running", progress: { current: 0, total: 0 } } },
      NOW,
    )
    expect(zero?.progressText).toBeNull()
  })
})

describe("timelinePhaseFor", () => {
  it("maps sub-phase and cost keys to timeline phases", () => {
    expect(timelinePhaseFor("phase_3_screening")).toBe("phase_3_screening")
    expect(timelinePhaseFor("phase_6b_phase_a")).toBe("phase_6_writing")
    expect(timelinePhaseFor("phase_4b_embedding")).toBe("phase_4b_embedding")
    expect(timelinePhaseFor("phase_4_pdf_vision_table_extraction")).toBe("phase_4_extraction_quality")
    expect(timelinePhaseFor("quality_rob2")).toBe("phase_4_extraction_quality")
    expect(timelinePhaseFor("screening_calibration")).toBe("phase_3_screening")
    expect(timelinePhaseFor("unknown_bucket")).toBeNull()
  })
})

describe("resume planning", () => {
  it("lists phases that re-run from a starting phase", () => {
    expect(phasesRerunFrom("phase_6_writing")).toEqual(["phase_6_writing", "phase_7_audit", "finalize"])
    expect(phasesRerunFrom("nope")).toEqual([])
  })

  it("sums prior cost of re-run phases, including sub-phase buckets", () => {
    const byPhase = [
      { phase: "phase_3_screening", cost_usd: 5 },
      { phase: "phase_6_writing", cost_usd: 1.5 },
      { phase: "phase_6b_phase_a", cost_usd: 0.5 },
      { phase: "phase_7_audit", cost_usd: 0.25 },
    ]
    expect(priorCostForPhases(byPhase, phasesRerunFrom("phase_6_writing"))).toBeCloseTo(2.25)
    expect(priorCostForPhases([], ["phase_6_writing"])).toBeNull()
    expect(priorCostForPhases(null, ["phase_6_writing"])).toBeNull()
  })

  it("marks only reachable phases as selectable and finds the latest one", () => {
    const states: Record<string, PhaseState> = {
      phase_1_prospero_gate: { status: "done" },
      phase_2_search: { status: "done" },
      phase_3_screening: { status: "error" },
    }
    const options = resumeOptions(states, false)
    expect(options.map((o) => o.phase)).toEqual([
      "phase_1_prospero_gate",
      "phase_2_search",
      "phase_3_screening",
      "phase_4_extraction_quality",
      "phase_4b_embedding",
      "phase_5_synthesis",
      "phase_5b_knowledge_graph",
      "phase_5c_pre_writing_gate",
      "phase_6_writing",
      "finalize",
    ])
    expect(options.filter((o) => o.selectable).map((o) => o.phase)).toEqual([
      "phase_1_prospero_gate",
      "phase_2_search",
      "phase_3_screening",
    ])
    expect(options[2].label).toBe("Study screening")
    expect(latestResumablePhase(states, false)).toBe("phase_3_screening")
    expect(latestResumablePhase({}, false)).toBeNull()
  })
})

describe("failure handling", () => {
  it("uses the last error event and the current phase", () => {
    const events: ReviewEvent[] = [
      { type: "error", msg: "first" },
      { type: "phase_start", phase: "phase_2_search", description: "", total: null, ts: "2026-03-12T00:00:00Z" },
      { type: "error", msg: "last" },
    ]
    const states: Record<string, PhaseState> = { phase_2_search: { status: "running" } }
    expect(failureSummary(events, states)).toEqual({ phase: "phase_2_search", message: "last" })
  })

  it("falls back to done.outputs.error, then a generic message", () => {
    expect(failureSummary([{ type: "done", outputs: { error: "boom" } }], {}).message).toBe("boom")
    expect(failureSummary([], {})).toEqual({ phase: null, message: "An unexpected error occurred." })
  })

  it("marks the failed sub-phase and its timeline parent as errored", () => {
    const states: Record<string, PhaseState> = {
      phase_5_synthesis: { status: "done" },
      phase_6_writing: { status: "running" },
      phase_6b_phase_a: { status: "running" },
    }
    const failed = applyFailure(states, currentPhaseId(states))
    expect(failed.phase_6_writing.status).toBe("error")
    expect(failed.phase_6b_phase_a.status).toBe("error")
    expect(failed.phase_5_synthesis.status).toBe("done")
    expect(applyFailure(states, null)).toBe(states)
  })
})
