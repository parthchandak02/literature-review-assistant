import { describe, expect, it } from "vitest"
import type { HistoryEntry } from "@/lib/api"
import {
  computeShouldShowStandaloneLiveCard,
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

  it("treats config_ready and config_generating as prospero pending", () => {
    const history = [
      historyEntry({ workflow_id: "wf-gen", status: "config_generating" }),
      historyEntry({ workflow_id: "wf-ready", status: "config_ready" }),
      historyEntry({ workflow_id: "wf-done", status: "completed" }),
    ]

    const { prosperoPendingHistory, inProgressHistory } = partitionHistory(history)

    expect(prosperoPendingHistory.map((e) => e.workflow_id)).toEqual(["wf-gen", "wf-ready"])
    expect(inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-done"])
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
