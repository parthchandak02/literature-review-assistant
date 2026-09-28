// @vitest-environment jsdom
import "@/test/dom"
import type { ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { HistoryEntry } from "@/lib/api"
import { IN_PROGRESS_PINS_STORAGE_KEY, useSidebarRuns } from "./useSidebarRuns"

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))
vi.mock("@/hooks/useNotesStream", () => ({ useNotesStream: () => {} }))

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
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(
    () => useSidebarRuns({ history, refetchHistory: vi.fn(), liveRun: null, ...handlers }),
    { wrapper },
  )
  return { ...hook, handlers }
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
  })

  it("archives immediately, then Undo restores the previous lane", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-1" })])

    await act(() => result.current.handleArchive("wf-1"))
    expect(handlers.onArchive).toHaveBeenCalledWith("wf-1")
    expect(toastMock).toHaveBeenCalledWith(
      'Archived "Effects of exercise on sleep quality"',
      expect.objectContaining({ action: expect.any(Object) }),
    )

    await act(async () => lastUndo()())
    expect(handlers.onRestore).toHaveBeenCalledWith("wf-1")
    expect(handlers.onHideCompleted).not.toHaveBeenCalled()
  })

  it("undoing an archive from the Completed lane puts it back in Completed", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-2", is_completed_hidden: true })])

    await act(() => result.current.handleArchive("wf-2"))
    await act(async () => lastUndo()())
    expect(handlers.onHideCompleted).toHaveBeenCalledWith("wf-2")
  })

  it("Move to In progress pins a finished run and Undo unpins it", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-3", status: "completed" })])
    expect(result.current.completedHistory.map((e) => e.workflow_id)).toEqual(["wf-3"])

    await act(() => result.current.handleMoveToInProgress("wf-3"))
    expect(result.current.inProgressHistory.map((e) => e.workflow_id)).toEqual(["wf-3"])
    expect(localStorage.getItem(IN_PROGRESS_PINS_STORAGE_KEY)).toContain("wf-3")
    expect(handlers.onRestoreCompleted).not.toHaveBeenCalled()

    await act(async () => lastUndo()())
    expect(result.current.completedHistory.map((e) => e.workflow_id)).toEqual(["wf-3"])
  })

  it("Move to Completed calls the API and Undo restores it", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-4" })])

    await act(() => result.current.handleMoveToCompleted("wf-4"))
    expect(handlers.onHideCompleted).toHaveBeenCalledWith("wf-4")
    await act(async () => lastUndo()())
    expect(handlers.onRestoreCompleted).toHaveBeenCalledWith("wf-4")
  })

  it("shows an error toast and no Undo when the move fails", async () => {
    const { result, handlers } = setup([entry({ workflow_id: "wf-5" })])
    handlers.onArchive.mockRejectedValueOnce(new Error("Cannot archive a run that is currently in progress"))

    await act(() => result.current.handleArchive("wf-5"))
    expect(toastMock).not.toHaveBeenCalled()
    expect(toastMock.error).toHaveBeenCalledWith("Cannot archive a run that is currently in progress")
  })
})
