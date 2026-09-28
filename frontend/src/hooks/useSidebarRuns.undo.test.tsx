// @vitest-environment jsdom
import "@/test/dom"
import type { ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { HistoryEntry } from "@/lib/api"
import {
  IN_PROGRESS_PINS_STORAGE_KEY,
  migrateLegacyInProgressPins,
  useSidebarRuns,
} from "./useSidebarRuns"

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }))
const setHistoryLaneMock = vi.hoisted(() => vi.fn(async () => {}))
vi.mock("sonner", () => ({ toast: toastMock }))
vi.mock("@/hooks/useNotesStream", () => ({ useNotesStream: () => {} }))
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, setHistoryLane: setHistoryLaneMock }
})

function entry(overrides: Partial<HistoryEntry> & Pick<HistoryEntry, "workflow_id">): HistoryEntry {
  return {
    topic: "Effects of exercise on sleep quality",
    status: "failed",
    db_path: "/tmp/runtime.db",
    created_at: "2026-03-10T10:00:00",
    is_archived: false,
    is_completed_hidden: false,
    ...overrides,
  }
}

function setup(history: HistoryEntry[]) {
  const handlers = {
    onSelectHistory: vi.fn(async () => {}),
    onResume: vi.fn(async () => {}),
    onArchive: vi.fn(async () => {}),
    onRestore: vi.fn(async () => {}),
    onHideCompleted: vi.fn(async () => {}),
    onRestoreCompleted: vi.fn(async () => {}),
    onDelete: vi.fn(async () => {}),
  }
  const refetchHistory = vi.fn()
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(
    () => useSidebarRuns({ history, refetchHistory, liveRun: null, ...handlers }),
    { wrapper },
  )
  return { ...hook, handlers, refetchHistory }
}

function lastUndo(): () => void {
  const call = toastMock.mock.calls.at(-1) as [string, { action: { label: string; onClick: () => void } }]
  expect(call[1].action.label).toBe("Undo")
  return call[1].action.onClick
}

describe("useSidebarRuns undo toasts", () => {
  beforeEach(() => {
    toastMock.mockClear()
    toastMock.error.mockClear()
    setHistoryLaneMock.mockClear()
    localStorage.clear()
  })

  it("archives immediately, then Undo restores the previous lane and reselects", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-1" })])

    await act(() => result.current.handleArchive("wf-1"))
    expect(handlers.onArchive).toHaveBeenCalledWith("wf-1")
    expect(toastMock).toHaveBeenCalledWith(
      'Archived "Effects of exercise on sleep quality"',
      expect.objectContaining({ action: expect.any(Object) }),
    )

    await act(async () => lastUndo()())
    expect(handlers.onRestore).toHaveBeenCalledWith("wf-1", { undo: true, lane: null })
    expect(handlers.onHideCompleted).not.toHaveBeenCalled()
  })

  it("undoing an archive from the Completed lane restores the Completed pin", async () => {
    const { result, handlers } = setup([
      entry({ workflow_id: "wf-2", is_completed_hidden: true, lane_override: "completed" }),
    ])

    await act(() => result.current.handleArchive("wf-2"))
    await act(async () => lastUndo()())
    expect(handlers.onRestore).toHaveBeenCalledWith("wf-2", { undo: true, lane: "completed" })
  })

  it("Move to In progress persists the pin on the server and Undo clears it", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-3", status: "completed" })])
    expect(result.current.completedHistory.map((e) => e.workflow_id)).toEqual(["wf-3"])

    await act(() => result.current.handleMoveToInProgress("wf-3"))
    expect(handlers.onRestoreCompleted).toHaveBeenCalledWith("wf-3", {
      undo: undefined,
      lane: "in_progress",
    })
    expect(localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY)).toBeNull()

    await act(async () => lastUndo()())
    expect(handlers.onRestoreCompleted).toHaveBeenLastCalledWith("wf-3", { undo: true, lane: null })
  })

  it("Move to Completed calls the API and Undo restores the previous lane", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-4", lane_override: "in_progress" })])

    await act(() => result.current.handleMoveToCompleted("wf-4"))
    expect(handlers.onHideCompleted).toHaveBeenCalledWith("wf-4", { undo: undefined })
    await act(async () => lastUndo()())
    expect(handlers.onRestoreCompleted).toHaveBeenCalledWith("wf-4", {
      undo: true,
      lane: "in_progress",
    })
  })

  it("shows an error toast and no Undo when the move fails", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-5" })])
    handlers.onArchive.mockRejectedValueOnce(new Error("Cannot archive a run that is currently in progress"))

    await act(() => result.current.handleArchive("wf-5"))
    expect(toastMock).not.toHaveBeenCalled()
    expect(toastMock.error).toHaveBeenCalledWith("Cannot archive a run that is currently in progress")
  })
})

describe("useSidebarRuns legacy pin migration", () => {
  beforeEach(() => {
    setHistoryLaneMock.mockClear()
    localStorage.clear()
  })

  it("pushes localStorage pins to the server once and clears them", async () => {
    localStorage.setItem(IN_PROGRESS_PINS_STORAGE_KEY, JSON.stringify(["wf-6"]))
    const { refetchHistory } = setup([entry({ workflow_id: "wf-6", status: "completed" })])

    await waitFor(() => expect(setHistoryLaneMock).toHaveBeenCalledWith("wf-6", "in_progress"))
    await waitFor(() => expect(refetchHistory).toHaveBeenCalled())
    expect(localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY)).toBeNull()
  })

  it("lets a server pin win, drops unknown reviews and keeps failed pushes", async () => {
    localStorage.setItem(
      IN_PROGRESS_PINS_STORAGE_KEY,
      JSON.stringify(["wf-server", "wf-gone", "wf-ok", "wf-fail"]),
    )
    const history = [
      entry({ workflow_id: "wf-server", status: "completed", is_completed_hidden: true }),
      entry({ workflow_id: "wf-ok", status: "completed" }),
      entry({ workflow_id: "wf-fail", status: "completed" }),
    ]
    const setLane = vi.fn(async (id: string) => {
      if (id === "wf-fail") throw new Error("boom")
    })

    const pinned = await migrateLegacyInProgressPins(history, setLane)
    expect(pinned).toEqual(["wf-ok"])
    expect(setLane.mock.calls.map((c) => c[0])).toEqual(["wf-ok", "wf-fail"])
    expect(JSON.parse(localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY) ?? "[]")).toEqual(["wf-fail"])
  })

  it("does nothing without legacy pins", async () => {
    const setLane = vi.fn(async () => {})
    expect(await migrateLegacyInProgressPins([entry({ workflow_id: "wf-7" })], setLane)).toEqual([])
    expect(setLane).not.toHaveBeenCalled()
  })
})
