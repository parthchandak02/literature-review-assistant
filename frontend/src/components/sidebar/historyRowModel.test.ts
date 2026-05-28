import { describe, expect, it } from "vitest"
import { buildInProgressRowModel } from "./historyRowModel"
import type { HistoryEntry } from "@/lib/api"
import type { LiveRun } from "./types"

const baseEntry: HistoryEntry = {
  workflow_id: "wf-1",
  topic: "Test topic",
  status: "stale",
  db_path: "/tmp/runtime.db",
  created_at: "2026-01-01T00:00:00Z",
  papers_found: 10,
  papers_included: 2,
  total_cost: 1.5,
  live_run_id: null,
  notes: null,
}

const liveRun: LiveRun = {
  runId: "run-live",
  topic: "Live topic",
  status: "streaming",
  cost: 0.5,
  workflowId: "wf-1",
  phaseProgress: { value: 0.4, completedPhases: 2 },
  startedAt: "2026-01-01T00:00:00Z",
  papersFound: 20,
  papersIncluded: 5,
}

describe("buildInProgressRowModel", () => {
  it("marks live row and uses live metrics", () => {
    const entry = { ...baseEntry, live_run_id: "run-live" }
    const model = buildInProgressRowModel(entry, liveRun, "wf-1", null, null, {})
    expect(model.isLiveRow).toBe(true)
    expect(model.rowIsRunning).toBe(true)
    expect(model.papersFound).toBe(20)
    expect(model.cost).toBe(0.5)
    expect(model.isSelected).toBe(true)
  })

  it("detects reconnecting stale streaming status without live_run_id", () => {
    const entry = { ...baseEntry, status: "streaming", live_run_id: null }
    const model = buildInProgressRowModel(entry, null, null, null, null, {})
    expect(model.isReconnectingRow).toBe(true)
    expect(model.rowIsRunning).toBe(true)
    expect(model.progressValue).toBe(-1)
  })

  it("allows resume for cancelled stale runs when handler provided", () => {
    const entry = { ...baseEntry, status: "cancelled" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {
      onResume: async () => {},
    })
    expect(model.isResumable).toBe(true)
    expect(model.actionPadClass).toBe("pr-14")
  })

  it("uses done progress for terminal history status", () => {
    const entry = { ...baseEntry, status: "completed" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {})
    expect(model.progressValue).toBe(1)
    expect(model.rowIsRunning).toBe(false)
  })
})
