import { describe, expect, it } from "vitest"
import type { HistoryEntry } from "@/lib/api"
import {
  computeShouldShowStandaloneLiveCard,
  defaultCompletedExpanded,
  laneOf,
  laneOverrideOf,
  partitionHistory,
} from "./useSidebarRuns"
import type { LiveRun } from "@/components/sidebar/types"

function historyEntry(
  overrides: Partial<HistoryEntry> & Pick<HistoryEntry, "workflow_id">,
): HistoryEntry {
  return {
    topic: "Topic",
    status: "completed",
    db_path: "/tmp/runtime.db",
    created_at: "2026-03-10T10:00:00",
    updated_at: null,
    papers_found: null,
    papers_included: null,
    total_cost: null,
    artifacts_count: null,
    stats_ok: null,
    stats_error: null,
    live_run_id: null,
    notes: null,
    is_archived: false,
    archived_at: null,
    is_completed_hidden: false,
    completed_hidden_at: null,
    ...overrides,
  }
}

describe("partitionHistory", () => {
  it("splits active, completed-hidden, archived, and prospero-pending rows", () => {
    const history = [
      historyEntry({ workflow_id: "wf-running", status: "running" }),
      historyEntry({ workflow_id: "wf-prospero", status: "awaiting_prospero" }),
      historyEntry({
        workflow_id: "wf-completed-hidden",
        status: "completed",
        is_completed_hidden: true,
        completed_hidden_at: "2026-03-10T12:00:00",
      }),
      historyEntry({
        workflow_id: "wf-archived",
        status: "completed",
        is_archived: true,
        archived_at: "2026-03-10T11:00:00",
      }),
    ]

    const partitions = partitionHistory(history)

    expect(partitions.inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-running"])
    expect(partitions.prosperoPendingHistory.map((e) => e.workflow_id)).toEqual(["wf-prospero"])
    expect(partitions.completedHistory.map((e) => e.workflow_id)).toEqual(["wf-completed-hidden"])
    expect(partitions.archivedHistory.map((e) => e.workflow_id)).toEqual(["wf-archived"])
    expect(partitions.visibleHistory.map((e) => e.workflow_id)).toEqual([
      "wf-running",
      "wf-prospero",
    ])
  })

  it("groups screening-review parked runs with other runs that need user input", () => {
    const history = [
      historyEntry({ workflow_id: "wf-review", status: "awaiting_review" }),
      historyEntry({ workflow_id: "wf-failed", status: "failed" }),
    ]
    const partitions = partitionHistory(history)
    expect(partitions.prosperoPendingHistory.map((e) => e.workflow_id)).toEqual(["wf-review"])
    expect(partitions.inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-failed"])
  })

  it("files finished runs into Completed even without the persisted flag (V3)", () => {
    const history = [
      historyEntry({ workflow_id: "wf-done", status: "completed" }),
      historyEntry({ workflow_id: "wf-running", status: "running" }),
      historyEntry({ workflow_id: "wf-live-done", status: "completed", live_run_id: "run-1" }),
    ]
    const partitions = partitionHistory(history)
    expect(partitions.completedHistory.map((e) => e.workflow_id)).toEqual(["wf-done"])
    expect(partitions.inProgressHistory.map((e) => e.workflow_id)).toEqual([
      "wf-running",
      "wf-live-done",
    ])
  })

  it("keeps a finished run in In progress when the server pin says so", () => {
    const history = [
      historyEntry({ workflow_id: "wf-done", status: "completed", lane_override: "in_progress" }),
    ]
    const partitions = partitionHistory(history)
    expect(partitions.completedHistory).toHaveLength(0)
    expect(partitions.inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-done"])
  })

  it("files an unfinished run into Completed when pinned there", () => {
    const entry = historyEntry({ workflow_id: "wf-x", status: "failed" })
    expect(laneOf(entry)).toBe("in-progress")
    expect(laneOf({ ...entry, lane_override: "completed" })).toBe("completed")
    expect(laneOf({ ...entry, is_completed_hidden: true })).toBe("completed")
  })

  it("lets the legacy Completed flag win over an In progress pin", () => {
    const entry = historyEntry({
      workflow_id: "wf-x",
      status: "failed",
      is_completed_hidden: true,
      lane_override: "in_progress",
    })
    expect(laneOverrideOf(entry)).toBe("completed")
    expect(laneOf(entry)).toBe("completed")
  })

  it("keeps an archived row archived whatever its lane pin", () => {
    const entry = historyEntry({ workflow_id: "wf-a", is_archived: true, lane_override: "in_progress" })
    expect(laneOf(entry)).toBe("archived")
  })

  it("puts config_ready in Needs your input and config_generating in In progress", () => {
    const history = [
      historyEntry({ workflow_id: "wf-gen", status: "config_generating", updated_at: new Date().toISOString() }),
      historyEntry({ workflow_id: "wf-ready", status: "config_ready" }),
      historyEntry({ workflow_id: "wf-stale", status: "stale" }),
    ]

    const { prosperoPendingHistory, inProgressHistory } = partitionHistory(history)

    expect(prosperoPendingHistory.map((e) => e.workflow_id)).toEqual(["wf-ready"])
    expect(inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-gen", "wf-stale"])
  })

  it("moves a stalled config_generating run to Needs your input", () => {
    const history = [
      historyEntry({ workflow_id: "wf-stalled", status: "config_generating", updated_at: "2026-01-01T00:00:00Z" }),
    ]
    const { prosperoPendingHistory, inProgressHistory } = partitionHistory(history)
    expect(prosperoPendingHistory.map((e) => e.workflow_id)).toEqual(["wf-stalled"])
    expect(inProgressHistory).toEqual([])
  })

  it("excludes archived rows from visible and completed partitions", () => {
    const history = [
      historyEntry({
        workflow_id: "wf-archived-completed",
        status: "completed",
        is_archived: true,
        is_completed_hidden: true,
      }),
    ]

    const partitions = partitionHistory(history)

    expect(partitions.archivedHistory).toHaveLength(1)
    expect(partitions.completedHistory).toHaveLength(0)
    expect(partitions.visibleHistory).toHaveLength(0)
  })
})

describe("computeShouldShowStandaloneLiveCard", () => {
  const liveRun: LiveRun = {
    runId: "run-live-1",
    topic: "Live topic",
    status: "streaming",
    cost: 0.5,
    workflowId: "wf-live-1",
  }

  it("returns true when live run has no matching history row", () => {
    const history = [historyEntry({ workflow_id: "wf-other", live_run_id: "run-other" })]

    expect(computeShouldShowStandaloneLiveCard(liveRun, history)).toBe(true)
  })

  it("returns false when history matches by workflow_id", () => {
    const history = [historyEntry({ workflow_id: "wf-live-1" })]

    expect(computeShouldShowStandaloneLiveCard(liveRun, history)).toBe(false)
  })

  it("returns false when history matches by live_run_id", () => {
    const history = [
      historyEntry({ workflow_id: "wf-other", live_run_id: "run-live-1" }),
    ]

    expect(computeShouldShowStandaloneLiveCard(liveRun, history)).toBe(false)
  })

  it("returns false when there is no live run", () => {
    expect(computeShouldShowStandaloneLiveCard(null, [])).toBe(false)
  })
})

describe("defaultCompletedExpanded", () => {
  const done = historyEntry({ workflow_id: "wf-done", status: "completed", updated_at: "2026-03-12T10:00:00" })

  it("stays closed when Completed is empty", () => {
    const partitions = partitionHistory([historyEntry({ workflow_id: "wf-run", status: "running" })])
    expect(defaultCompletedExpanded(partitions, false)).toBe(false)
  })

  it("opens when nothing is in progress, even with drafts waiting for input", () => {
    const partitions = partitionHistory([
      done,
      historyEntry({ workflow_id: "wf-draft", status: "awaiting_prospero", updated_at: "2026-03-13T10:00:00" }),
    ])
    expect(defaultCompletedExpanded(partitions, false)).toBe(true)
  })

  it("opens when the most recently updated review is completed", () => {
    const partitions = partitionHistory([
      done,
      historyEntry({ workflow_id: "wf-old", status: "failed", updated_at: "2026-03-01T10:00:00" }),
    ])
    expect(defaultCompletedExpanded(partitions, false)).toBe(true)
  })

  it("stays closed when newer work is in progress", () => {
    const partitions = partitionHistory([
      done,
      historyEntry({ workflow_id: "wf-new", status: "failed", updated_at: "2026-03-14T10:00:00" }),
    ])
    expect(defaultCompletedExpanded(partitions, false)).toBe(false)
    expect(defaultCompletedExpanded(partitionHistory([done]), true)).toBe(false)
  })
})
