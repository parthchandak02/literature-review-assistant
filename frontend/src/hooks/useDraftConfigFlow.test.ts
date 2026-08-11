import { describe, expect, it } from "vitest"
import {
  deriveDraftStatus,
  deriveIsDraftRun,
  deriveResolvedHistoricalStatus,
} from "./useDraftConfigFlow"
import type { SelectedRun } from "@/context/runSessionTypes"
import type { DraftConfigState } from "./useDraftConfigFlow"

function selectedRunFixture(
  overrides: Partial<SelectedRun> = {},
): SelectedRun {
  return {
    runId: "wf-1",
    workflowId: "wf-1",
    topic: "Test question",
    dbPath: "/tmp/db.sqlite",
    isDone: false,
    startedAt: null,
    ...overrides,
  }
}

function draftConfigFixture(
  overrides: Partial<DraftConfigState> = {},
): DraftConfigState {
  return {
    request: {
      question: "Test question",
      deepseekKey: "key",
      csvMode: "supplementary",
      generationProfile: "standard",
    },
    yaml: "",
    isGenerating: false,
    activeStep: "start",
    stepMetadata: {},
    usedWebFallback: false,
    fallbackReason: null,
    generationError: null,
    ...overrides,
  }
}

describe("deriveIsDraftRun", () => {
  it("returns false when no run is selected", () => {
    expect(deriveIsDraftRun(null, null)).toBe(false)
    expect(deriveIsDraftRun(null, draftConfigFixture())).toBe(false)
  })

  it("detects draft workflow id", () => {
    expect(deriveIsDraftRun(selectedRunFixture({ workflowId: "draft" }), null)).toBe(true)
  })

  it("detects active draft config state", () => {
    expect(deriveIsDraftRun(selectedRunFixture(), draftConfigFixture())).toBe(true)
  })

  it("detects config draft historical statuses", () => {
    expect(
      deriveIsDraftRun(selectedRunFixture({ historicalStatus: "config_generating" }), null),
    ).toBe(true)
    expect(
      deriveIsDraftRun(selectedRunFixture({ historicalStatus: "config_ready" }), null),
    ).toBe(true)
  })

  it("returns false for normal completed runs without draft state", () => {
    expect(
      deriveIsDraftRun(selectedRunFixture({ historicalStatus: "completed" }), null),
    ).toBe(false)
  })
})

describe("deriveDraftStatus", () => {
  it("prefers generating draft config over historical status", () => {
    expect(deriveDraftStatus(draftConfigFixture({ isGenerating: true }), "config_ready")).toBe(
      "config_generating",
    )
  })

  it("uses historical config_generating when draft is not generating", () => {
    expect(deriveDraftStatus(null, "config_generating")).toBe("config_generating")
  })

  it("returns config_ready from historical status", () => {
    expect(deriveDraftStatus(null, "config_ready")).toBe("config_ready")
  })

  it("returns idle when no draft signals are present", () => {
    expect(deriveDraftStatus(null, "completed")).toBe("idle")
    expect(deriveDraftStatus(draftConfigFixture(), "completed")).toBe("idle")
  })
})

describe("deriveResolvedHistoricalStatus", () => {
  it("returns idle when no run is selected", () => {
    expect(deriveResolvedHistoricalStatus(null, false, "idle")).toBe("idle")
  })

  it("returns draft status for draft runs", () => {
    const run = selectedRunFixture({ historicalStatus: "config_generating" })
    expect(deriveResolvedHistoricalStatus(run, true, "config_generating")).toBe("config_generating")
    expect(deriveResolvedHistoricalStatus(run, true, "config_ready")).toBe("config_ready")
  })

  it("maps non-draft historical statuses via resolveRunStatus", () => {
    const run = selectedRunFixture({ historicalStatus: "completed" })
    expect(deriveResolvedHistoricalStatus(run, false, "idle")).toBe("done")
    expect(
      deriveResolvedHistoricalStatus(
        selectedRunFixture({ historicalStatus: "failed" }),
        false,
        "idle",
      ),
    ).toBe("error")
  })
})
