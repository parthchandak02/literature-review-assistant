import { describe, expect, it } from "vitest"
import type { HistoryEntry } from "@/lib/api"
import type { SelectedRun } from "@/context/runSessionTypes"
import {
  resolveHistorySelectTransition,
  selectedRunToHistoryEntry,
  type HistorySelectContext,
} from "./runSessionSelection"

function makeEntry(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    workflow_id: "wf-001",
    topic: "Test topic",
    status: "running",
    db_path: "/data/wf-001.db",
    created_at: "2026-01-01T00:00:00.000Z",
    live_run_id: null,
    ...overrides,
  }
}

function makeSelectedRun(overrides: Partial<SelectedRun> = {}): SelectedRun {
  return {
    runId: "run-live",
    workflowId: "wf-001",
    topic: "Test topic",
    dbPath: "/data/wf-001.db",
    isDone: false,
    startedAt: null,
    ...overrides,
  }
}

describe("resolveHistorySelectTransition", () => {
  describe("focus_same_run", () => {
    it("returns focus_same_run when active run matches current selection", () => {
      const entry = makeEntry()
      const ctx: HistorySelectContext = {
        liveRunId: "run-live",
        selectedRun: makeSelectedRun(),
      }
      const active = { run_id: "run-live", topic: "Live topic" }

      expect(resolveHistorySelectTransition(entry, ctx, active)).toEqual({
        kind: "focus_same_run",
      })
    })

    it("returns focus_same_run when entry live_run_id matches current selection", () => {
      const entry = makeEntry({ live_run_id: "run-live" })
      const ctx: HistorySelectContext = {
        liveRunId: "run-live",
        selectedRun: makeSelectedRun(),
      }

      expect(resolveHistorySelectTransition(entry, ctx, null)).toEqual({
        kind: "focus_same_run",
      })
    })
  })

  describe("connect_live", () => {
    it("returns connect_live from active run when selection differs", () => {
      const entry = makeEntry()
      const ctx: HistorySelectContext = {
        liveRunId: "other-run",
        selectedRun: makeSelectedRun({ runId: "other-run", workflowId: "wf-other" }),
      }
      const active = { run_id: "run-live", topic: "Active topic" }

      expect(resolveHistorySelectTransition(entry, ctx, active)).toEqual({
        kind: "connect_live",
        entry,
        runId: "run-live",
        topic: "Active topic",
      })
    })

    it("falls back to entry topic when active topic is empty", () => {
      const entry = makeEntry({ topic: "Entry topic" })
      const ctx: HistorySelectContext = {
        liveRunId: null,
        selectedRun: null,
      }
      const active = { run_id: "run-live", topic: "" }

      expect(resolveHistorySelectTransition(entry, ctx, active)).toEqual({
        kind: "connect_live",
        entry,
        runId: "run-live",
        topic: "Entry topic",
      })
    })

    it("returns connect_live from entry live_run_id when no active run", () => {
      const entry = makeEntry({ live_run_id: "run-live" })
      const ctx: HistorySelectContext = {
        liveRunId: null,
        selectedRun: null,
      }

      expect(resolveHistorySelectTransition(entry, ctx, null)).toEqual({
        kind: "connect_live",
        entry,
        runId: "run-live",
        topic: "Test topic",
      })
    })
  })

  describe("attach_historical", () => {
    it("returns attach_historical when no active run and no live_run_id", () => {
      const entry = makeEntry({ status: "completed", live_run_id: null })
      const ctx: HistorySelectContext = {
        liveRunId: null,
        selectedRun: null,
      }

      expect(resolveHistorySelectTransition(entry, ctx, null)).toEqual({
        kind: "attach_historical",
        entry,
      })
    })
  })
})

describe("selectedRunToHistoryEntry", () => {
  it("returns null when workflowId or dbPath is missing", () => {
    expect(selectedRunToHistoryEntry(makeSelectedRun({ workflowId: null }))).toBeNull()
    expect(selectedRunToHistoryEntry(makeSelectedRun({ dbPath: null }))).toBeNull()
    expect(selectedRunToHistoryEntry(null)).toBeNull()
  })

  it("maps selected run fields and defaults status to stale", () => {
    const entry = selectedRunToHistoryEntry(
      makeSelectedRun({
        historicalStatus: undefined,
        papersFound: 10,
        papersIncluded: 3,
        historicalCost: 1.25,
        createdAt: "2026-02-01T12:00:00.000Z",
      }),
    )
    expect(entry).toMatchObject({
      workflow_id: "wf-001",
      topic: "Test topic",
      status: "stale",
      db_path: "/data/wf-001.db",
      papers_found: 10,
      papers_included: 3,
      total_cost: 1.25,
      live_run_id: null,
    })
  })
})
