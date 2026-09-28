// @vitest-environment jsdom
import "@/test/dom"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { SelectedRun } from "@/context/runSessionTypes"
import { isScreeningResumeError, useRunGateActions } from "./useRunGateActions"

const api = vi.hoisted(() => ({
  approveScreening: vi.fn(),
  resumeRun: vi.fn(),
  fetchActiveRun: vi.fn(),
  fetchHistory: vi.fn(),
}))

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, ...api }
})

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const selectedRun: SelectedRun = {
  runId: "run-1",
  workflowId: "wf-1",
  topic: "Topic",
  dbPath: "/tmp/run.db",
  isDone: false,
  startedAt: null,
}

function setup() {
  const handleResumeRun = vi.fn()
  const client = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const { result } = renderHook(() => useRunGateActions({ selectedRun, handleResumeRun }), { wrapper })
  return { result, handleResumeRun }
}

describe("handleApproveScreeningAndResume", () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
  })

  it("approves then resumes", async () => {
    api.approveScreening.mockResolvedValue(undefined)
    api.resumeRun.mockResolvedValue({ run_id: "run-2" })
    const { result, handleResumeRun } = setup()
    const overrides = [{ paper_id: "p1", decision: "exclude" as const }]
    await act(() => result.current.handleApproveScreeningAndResume("run-1", overrides))
    expect(api.approveScreening).toHaveBeenCalledWith("run-1", overrides)
    expect(handleResumeRun).toHaveBeenCalledWith({ run_id: "run-2" }, "wf-1")
  })

  it("throws a plain error and does not resume when approval fails", async () => {
    api.approveScreening.mockRejectedValue(new Error("400 bad"))
    const { result } = setup()
    const err = await result.current.handleApproveScreeningAndResume("run-1").catch((e: unknown) => e)
    expect(isScreeningResumeError(err)).toBe(false)
    expect(api.resumeRun).not.toHaveBeenCalled()

    api.approveScreening.mockResolvedValue(undefined)
    api.resumeRun.mockResolvedValue({ run_id: "run-2" })
    await act(() => result.current.handleApproveScreeningAndResume("run-1"))
    expect(api.approveScreening).toHaveBeenCalledTimes(2)
  })

  it("throws ScreeningResumeError when resume fails, and the retry skips the approval POST", async () => {
    api.approveScreening.mockResolvedValue(undefined)
    api.resumeRun.mockRejectedValueOnce(new Error("500 resume broke"))
    const { result, handleResumeRun } = setup()

    const err = await result.current.handleApproveScreeningAndResume("run-1").catch((e: unknown) => e)
    expect(isScreeningResumeError(err)).toBe(true)
    expect((err as Error).message).toBe("500 resume broke")
    expect(api.approveScreening).toHaveBeenCalledTimes(1)

    api.resumeRun.mockResolvedValueOnce({ run_id: "run-3" })
    await act(() => result.current.handleApproveScreeningAndResume("run-1"))
    expect(api.approveScreening).toHaveBeenCalledTimes(1)
    expect(api.resumeRun).toHaveBeenCalledTimes(2)
    expect(handleResumeRun).toHaveBeenCalledWith({ run_id: "run-3" }, "wf-1")
  })

  it("treats a 409 resume as success when the run is already active", async () => {
    api.approveScreening.mockResolvedValue(undefined)
    api.resumeRun.mockRejectedValue(new Error("409 already running"))
    api.fetchActiveRun.mockResolvedValue({ run_id: "live" })
    const { result, handleResumeRun } = setup()
    await act(() => result.current.handleApproveScreeningAndResume("run-1"))
    expect(handleResumeRun).toHaveBeenCalledWith({ run_id: "live" }, "wf-1")
  })
})
