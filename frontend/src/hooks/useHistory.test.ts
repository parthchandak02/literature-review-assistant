import { describe, expect, it, vi, beforeEach } from "vitest"
import { railEntryToHistoryEntry } from "@/lib/api"
import type { HistoryEntry, HistoryRailEntry } from "@/lib/api"
import {
  createHistoryQueryFn,
  fetchSidebarHistory,
  HISTORY_REFRESH_MS,
  historyQueryKey,
  mergeHistoryStats,
  resolveHistoryRefetchInterval,
} from "./useHistory"

const fetchHistoryRailMock = vi.fn()

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    fetchHistoryRail: (...args: unknown[]) => fetchHistoryRailMock(...args),
  }
})

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

function railEntry(
  overrides: Partial<HistoryRailEntry> & Pick<HistoryRailEntry, "workflow_id">,
): HistoryRailEntry {
  return {
    topic: "Topic",
    status: "completed",
    db_path: "/tmp/runtime.db",
    created_at: "2026-03-10T10:00:00",
    live_run_id: null,
    notes: null,
    is_archived: false,
    is_completed_hidden: false,
    ...overrides,
  }
}

describe("resolveHistoryRefetchInterval", () => {
  it("returns false when SSE owns updates for the active live run", () => {
    expect(resolveHistoryRefetchInterval(true, true)).toBe(false)
  })

  it("returns HISTORY_REFRESH_MS when not viewing a live run", () => {
    expect(resolveHistoryRefetchInterval(true, false)).toBe(HISTORY_REFRESH_MS)
  })

  it("returns HISTORY_REFRESH_MS when viewing a live run that is not running", () => {
    expect(resolveHistoryRefetchInterval(false, true)).toBe(HISTORY_REFRESH_MS)
  })

  it("returns HISTORY_REFRESH_MS when idle and not viewing a live run", () => {
    expect(resolveHistoryRefetchInterval(false, false)).toBe(HISTORY_REFRESH_MS)
  })
})

describe("historyQueryKey", () => {
  it("includes run root so cache keys differ by registry root", () => {
    expect(historyQueryKey()).toEqual(["history", "runs"])
    expect(historyQueryKey("custom-root")).toEqual(["history", "custom-root"])
    expect(historyQueryKey()).not.toEqual(historyQueryKey("custom-root"))
  })
})

describe("railEntryToHistoryEntry", () => {
  const rail: HistoryRailEntry = {
    workflow_id: "wf-rail-1",
    topic: "Rail topic",
    status: "completed",
    db_path: "/tmp/runtime.db",
    created_at: "2026-03-10T10:00:00",
    live_run_id: null,
    notes: "sidebar note",
    is_archived: false,
    is_completed_hidden: false,
    papers_found: 42,
    papers_included: 7,
    total_cost: 3.5,
    stats_ok: true,
  }

  it("maps rail fields and fills omitted HistoryEntry fields with defaults", () => {
    const entry = railEntryToHistoryEntry(rail)
    expect(entry).toEqual({
      workflow_id: "wf-rail-1",
      topic: "Rail topic",
      status: "completed",
      db_path: "/tmp/runtime.db",
      created_at: "2026-03-10T10:00:00",
      updated_at: null,
      papers_found: 42,
      papers_included: 7,
      total_cost: 3.5,
      artifacts_count: null,
      stats_ok: true,
      stats_error: null,
      live_run_id: null,
      notes: "sidebar note",
      is_archived: false,
      archived_at: null,
      is_completed_hidden: false,
      completed_hidden_at: null,
    })
  })
})

describe("mergeHistoryStats", () => {
  it("carries papers_found, papers_included, total_cost, and stats_ok from previous rows", () => {
    const previous = [
      historyEntry({
        workflow_id: "wf-1",
        topic: "Old topic",
        papers_found: 42,
        papers_included: 7,
        total_cost: 3.5,
        stats_ok: true,
      }),
    ]
    const fresh = [
      historyEntry({
        workflow_id: "wf-1",
        topic: "Updated topic",
        status: "running",
        papers_found: null,
        papers_included: null,
        total_cost: null,
        stats_ok: null,
      }),
    ]

    expect(mergeHistoryStats(fresh, previous)).toEqual([
      historyEntry({
        workflow_id: "wf-1",
        topic: "Updated topic",
        status: "running",
        papers_found: 42,
        papers_included: 7,
        total_cost: 3.5,
        stats_ok: true,
      }),
    ])
  })

  it("leaves new workflows without cached stats unchanged", () => {
    const previous = [
      historyEntry({
        workflow_id: "wf-1",
        papers_found: 10,
        papers_included: 2,
        total_cost: 1.25,
        stats_ok: true,
      }),
    ]
    const fresh = [
      historyEntry({ workflow_id: "wf-1", papers_found: null }),
      historyEntry({ workflow_id: "wf-2", topic: "New run" }),
    ]

    const merged = mergeHistoryStats(fresh, previous)
    expect(merged[0]?.papers_found).toBe(10)
    expect(merged[1]).toEqual(fresh[1])
  })
})

describe("fetchSidebarHistory", () => {
  beforeEach(() => {
    fetchHistoryRailMock.mockReset()
  })

  it("requests stats=true on the initial full fetch", async () => {
    fetchHistoryRailMock.mockResolvedValue([
      railEntry({
        workflow_id: "wf-1",
        papers_found: 5,
        papers_included: 1,
        total_cost: 0.5,
        stats_ok: true,
      }),
    ])

    const result = await fetchSidebarHistory()

    expect(fetchHistoryRailMock).toHaveBeenCalledWith({ runRoot: "runs", stats: true })
    expect(result[0]?.papers_found).toBe(5)
    expect(result[0]?.papers_included).toBe(1)
    expect(result[0]?.total_cost).toBe(0.5)
  })

  it("requests stats=false and merges metrics from previous cache on poll fetch", async () => {
    const previous = [
      historyEntry({
        workflow_id: "wf-1",
        papers_found: 42,
        papers_included: 7,
        total_cost: 3.5,
        stats_ok: true,
      }),
    ]
    fetchHistoryRailMock.mockResolvedValue([
      railEntry({
        workflow_id: "wf-1",
        topic: "Updated topic",
        status: "running",
      }),
    ])

    const result = await fetchSidebarHistory("runs", { stats: false, previous })

    expect(fetchHistoryRailMock).toHaveBeenCalledWith({ runRoot: "runs", stats: false })
    expect(result[0]).toMatchObject({
      workflow_id: "wf-1",
      topic: "Updated topic",
      status: "running",
      papers_found: 42,
      papers_included: 7,
      total_cost: 3.5,
      stats_ok: true,
    })
  })
})

describe("createHistoryQueryFn", () => {
  beforeEach(() => {
    fetchHistoryRailMock.mockReset()
  })

  it("uses stats=true when query cache is empty", async () => {
    fetchHistoryRailMock.mockResolvedValue([railEntry({ workflow_id: "wf-1" })])
    const client = {
      getQueryData: vi.fn().mockReturnValue(undefined),
    }

    await createHistoryQueryFn()({ client } as never)

    expect(fetchHistoryRailMock).toHaveBeenCalledWith({ runRoot: "runs", stats: true })
  })

  it("uses stats=false and merges when cached history exists", async () => {
    const cached = [
      historyEntry({
        workflow_id: "wf-1",
        papers_found: 99,
        papers_included: 11,
        total_cost: 9.99,
        stats_ok: true,
      }),
    ]
    fetchHistoryRailMock.mockResolvedValue([
      railEntry({ workflow_id: "wf-1", topic: "Polled topic" }),
    ])
    const client = {
      getQueryData: vi.fn().mockReturnValue(cached),
    }

    const result = await createHistoryQueryFn()({ client } as never)

    expect(fetchHistoryRailMock).toHaveBeenCalledWith({ runRoot: "runs", stats: false })
    expect(result[0]).toMatchObject({
      topic: "Polled topic",
      papers_found: 99,
      papers_included: 11,
      total_cost: 9.99,
      stats_ok: true,
    })
    expect(client.getQueryData).toHaveBeenCalledWith(historyQueryKey())
  })
})
