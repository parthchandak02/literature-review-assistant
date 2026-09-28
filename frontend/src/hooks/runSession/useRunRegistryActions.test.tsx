// @vitest-environment jsdom
import "@/test/dom"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { SelectedRun } from "@/context/runSessionTypes"
import { useRunRegistryActions } from "./useRunRegistryActions"

const api = vi.hoisted(() => ({
  archiveRun: vi.fn(async () => {}),
  deleteRun: vi.fn(async () => {}),
  hideCompletedRun: vi.fn(async () => {}),
  restoreCompletedRun: vi.fn(async () => {}),
  restoreRun: vi.fn(async () => {}),
  setHistoryLane: vi.fn(async () => {}),
}))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, ...api }
})

const viewed: SelectedRun = {
  runId: "run-1",
  workflowId: "wf-1",
  topic: "Topic",
  dbPath: "/tmp/run.db",
  isDone: true,
  startedAt: null,
}

function setup(selectedRun: SelectedRun | null = viewed) {
  const deps = {
    navigate: vi.fn(),
    selectedRun,
    setSelectedRun: vi.fn(),
    setActiveRunTab: vi.fn(),
  }
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useRunRegistryActions(deps), { wrapper })
  return { result, deps }
}

describe("useRunRegistryActions archive undo", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockClear()
    window.history.replaceState(null, "", "/run/wf-1/database")
  })

  it("archiving the viewed run goes home, and Undo reselects it on the same tab", async () => {
    const { result, deps } = setup()

    await act(() => result.current.handleSidebarArchive("wf-1"))
    expect(deps.setSelectedRun).toHaveBeenLastCalledWith(null)
    expect(deps.navigate).toHaveBeenLastCalledWith("/", { replace: true })

    await act(() => result.current.handleSidebarRestore("wf-1", { undo: true, lane: "completed" }))
    expect(api.restoreRun).toHaveBeenCalledWith("wf-1")
    expect(api.setHistoryLane).toHaveBeenCalledWith("wf-1", "completed")
    expect(deps.setSelectedRun).toHaveBeenLastCalledWith(viewed)
    expect(deps.setActiveRunTab).toHaveBeenLastCalledWith("database")
    expect(deps.navigate).toHaveBeenLastCalledWith("/run/wf-1/database", { replace: true })
  })

  it("Move to Completed on the viewed run goes home, and Undo restores the lane and reselects", async () => {
    const { result, deps } = setup()

    await act(() => result.current.handleSidebarHideCompleted("wf-1"))
    expect(deps.navigate).toHaveBeenLastCalledWith("/", { replace: true })

    await act(() =>
      result.current.handleSidebarRestoreCompleted("wf-1", { undo: true, lane: "in_progress" }),
    )
    expect(api.setHistoryLane).toHaveBeenCalledWith("wf-1", "in_progress")
    expect(api.restoreCompletedRun).not.toHaveBeenCalled()
    expect(deps.navigate).toHaveBeenLastCalledWith("/run/wf-1/database", { replace: true })
  })

  it("a plain restore does not reselect", async () => {
    const { result, deps } = setup()

    await act(() => result.current.handleSidebarArchive("wf-1"))
    deps.navigate.mockClear()
    await act(() => result.current.handleSidebarRestore("wf-1"))
    expect(api.setHistoryLane).not.toHaveBeenCalled()
    expect(deps.navigate).not.toHaveBeenCalled()
  })

  it("archiving a run that is not on screen stays put and Undo does not navigate", async () => {
    const { result, deps } = setup(null)

    await act(() => result.current.handleSidebarArchive("wf-1"))
    await act(() => result.current.handleSidebarRestore("wf-1", { undo: true, lane: null }))
    expect(deps.navigate).not.toHaveBeenCalled()
    expect(deps.setSelectedRun).not.toHaveBeenCalled()
  })
})
