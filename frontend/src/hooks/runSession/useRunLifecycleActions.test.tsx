// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import type { HistoryEntry } from "@/lib/api"
import type { SelectedRun } from "@/context/runSessionTypes"
import type { RunSessionLifecycleActionDeps } from "@/hooks/runSession/runSessionActionDeps"
import type { RunSessionLiveConnectHandles } from "@/hooks/runSession/useRunLiveConnect"
import { sidebarSelectTab, useRunLifecycleActions } from "./useRunLifecycleActions"

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const gated: HistoryEntry = {
  workflow_id: "wf-1",
  topic: "Topic",
  status: "awaiting_review",
  db_path: "/tmp/runtime.db",
  created_at: "2026-09-01T00:00:00",
}

const viewed: SelectedRun = {
  runId: "run-1",
  workflowId: "wf-1",
  topic: "Topic",
  dbPath: "/tmp/runtime.db",
  isDone: false,
  startedAt: null,
}

function setup(selectedRun: SelectedRun | null) {
  const deps = {
    navigate: vi.fn(),
    selectedRun,
    setSelectedRun: vi.fn(),
    setActiveRunTab: vi.fn(),
    live: {
      liveRunId: null,
      abort: vi.fn(),
      clearLiveRunUi: vi.fn(),
      reset: vi.fn(),
      setLiveRunId: vi.fn(),
      setLiveTopic: vi.fn(),
      setLiveStartedAt: vi.fn(),
      setLiveWorkflowId: vi.fn(),
      liveRunNavigatedRef: { current: null },
      wasStreamingRef: { current: false },
    },
  } as unknown as RunSessionLifecycleActionDeps
  const liveConnect = {
    beginLiveRunFromResponse: vi.fn(),
    handleResumeRun: vi.fn(),
    selectedRunToHistoryEntry: vi.fn(),
  } as unknown as RunSessionLiveConnectHandles
  const { result } = renderHook(() => useRunLifecycleActions(deps, liveConnect))
  return { result, deps }
}

describe("sidebarSelectTab", () => {
  it("opens gated runs on their action tab", () => {
    expect(sidebarSelectTab("awaiting_review")).toBe("review-screening")
    expect(sidebarSelectTab("awaiting_prospero")).toBe("config")
    expect(sidebarSelectTab("config_ready")).toBe("config")
    expect(sidebarSelectTab("completed")).toBe("activity")
    expect(sidebarSelectTab(null)).toBe("activity")
  })
})

describe("handleSelectHistory", () => {
  it("re-clicking the awaiting_review run on screen routes to the screening tab", async () => {
    const { result, deps } = setup(viewed)

    await act(() => result.current.handleSelectHistory(gated))
    expect(deps.setActiveRunTab).toHaveBeenCalledWith("review-screening")
    expect(deps.navigate).toHaveBeenCalledWith("/run/wf-1/review-screening", { replace: true })
  })
})
