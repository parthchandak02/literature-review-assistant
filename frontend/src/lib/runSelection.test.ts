import { describe, expect, it } from "vitest"
import {
  isSameRunSelection,
  shouldFallbackToWorkflowEvents,
  shouldUsePrefetchedHistorical,
} from "./runSelection"

describe("runSelection guards", () => {
  it("detects same-run selection and avoids unnecessary reset path", () => {
    expect(isSameRunSelection("run-1", "run-1", "wf-1", "run-1", "wf-1")).toBe(true)
    expect(isSameRunSelection("run-1", "run-1", "wf-1", "run-2", "wf-1")).toBe(false)
    expect(isSameRunSelection("run-1", "run-1", "wf-1", "run-1", "wf-2")).toBe(false)
  })

  it("falls back to workflow replay when run replay is empty", () => {
    expect(shouldFallbackToWorkflowEvents(0, "wf-1", "run-1")).toBe(true)
    expect(shouldFallbackToWorkflowEvents(1, "wf-1", "run-1")).toBe(false)
    expect(shouldFallbackToWorkflowEvents(0, null, "run-1")).toBe(false)
    expect(shouldFallbackToWorkflowEvents(0, "run-1", "run-1")).toBe(false)
  })

  it("uses prefetched historical events only when non-empty", () => {
    expect(shouldUsePrefetchedHistorical(null)).toBe(false)
    expect(shouldUsePrefetchedHistorical([])).toBe(false)
    expect(shouldUsePrefetchedHistorical([{ type: "phase_start" }])).toBe(true)
  })
})
