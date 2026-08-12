import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  createWorkflowActiveRunWatcher,
  type WorkflowActiveRunWatcherDeps,
} from "@/hooks/workflowActiveRunWatcher"

function createDeps(
  overrides: Partial<WorkflowActiveRunWatcherDeps> = {},
): WorkflowActiveRunWatcherDeps & {
  focusListeners: Set<() => void>
  subscribeCallbacks: {
    onAnnouncement?: (event: { workflow_id: string; run_id: string; topic: string }) => void
    onError?: () => void
  }
  timeouts: Array<{ fn: () => void; delay: number }>
} {
  const focusListeners = new Set<() => void>()
  const subscribeCallbacks: {
    onAnnouncement?: (event: { workflow_id: string; run_id: string; topic: string }) => void
    onError?: () => void
  } = {}
  const timeouts: Array<{ fn: () => void; delay: number }> = []
  let timeoutId = 0

  return {
    focusListeners,
    subscribeCallbacks,
    timeouts,
    fetchActiveRun: vi.fn().mockResolvedValue(null),
    subscribeWorkflowActiveRun: vi.fn((_workflowId, callbacks) => {
      subscribeCallbacks.onAnnouncement = callbacks.onAnnouncement
      subscribeCallbacks.onError = callbacks.onError
      return vi.fn()
    }),
    addWindowFocusListener: (listener) => {
      focusListeners.add(listener)
    },
    removeWindowFocusListener: (listener) => {
      focusListeners.delete(listener)
    },
    setTimeout: ((fn: () => void, delay?: number) => {
      const id = ++timeoutId
      timeouts.push({ fn, delay: delay ?? 0 })
      return id as unknown as ReturnType<typeof setTimeout>
    }) as typeof setTimeout,
    clearTimeout: vi.fn(),
    ...overrides,
  }
}

describe("createWorkflowActiveRunWatcher", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("subscribes to workflow SSE and performs initial fetchActiveRun fallback", async () => {
    const deps = createDeps()
    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun: vi.fn(),
      },
      deps,
    )

    expect(deps.subscribeWorkflowActiveRun).toHaveBeenCalledWith("wf-1", expect.any(Object))
    await Promise.resolve()
    expect(deps.fetchActiveRun).toHaveBeenCalledWith("wf-1")
  })

  it("connects on SSE announcement and disposes subscription", () => {
    const onActiveRun = vi.fn()
    const unsubscribe = vi.fn()
    const deps = createDeps({
      subscribeWorkflowActiveRun: vi.fn((_workflowId, callbacks) => {
        deps.subscribeCallbacks.onAnnouncement = callbacks.onAnnouncement
        return unsubscribe
      }),
    })

    const watcher = createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun,
      },
      deps,
    )

    deps.subscribeCallbacks.onAnnouncement?.({
      workflow_id: "wf-1",
      run_id: "run-live",
      topic: "Live topic",
    })

    expect(onActiveRun).toHaveBeenCalledWith({ run_id: "run-live", topic: "Live topic" })
    expect(unsubscribe).toHaveBeenCalledTimes(1)
    watcher.dispose()
  })

  it("uses fetchActiveRun fallback on SSE error", async () => {
    const onActiveRun = vi.fn()
    const deps = createDeps({
      fetchActiveRun: vi.fn().mockResolvedValue({
        run_id: "run-fallback",
        topic: "Fallback topic",
      }),
    })

    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun,
      },
      deps,
    )

    deps.subscribeCallbacks.onError?.()
    await Promise.resolve()

    expect(deps.fetchActiveRun).toHaveBeenCalledWith("wf-1")
    expect(onActiveRun).toHaveBeenCalledWith({
      run_id: "run-fallback",
      topic: "Fallback topic",
    })
  })

  it("uses fetchActiveRun fallback on window focus", async () => {
    const onActiveRun = vi.fn()
    const deps = createDeps({
      fetchActiveRun: vi.fn().mockResolvedValue({
        run_id: "run-focus",
        topic: "Focus topic",
      }),
    })

    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun,
      },
      deps,
    )

    for (const listener of deps.focusListeners) listener()
    await Promise.resolve()

    expect(onActiveRun).toHaveBeenCalledWith({
      run_id: "run-focus",
      topic: "Focus topic",
    })
  })

  it("backs off fallback polling while the workflow SSE subscription stays healthy", async () => {
    const onActiveRun = vi.fn()
    const deps = createDeps({
      fetchActiveRun: vi.fn().mockResolvedValue(null),
    })

    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun,
      },
      deps,
    )

    expect(deps.timeouts[0]?.delay).toBe(30_000)
    deps.timeouts[0]?.fn()
    await Promise.resolve()
    expect(deps.timeouts[1]?.delay).toBe(60_000)
  })

  it("uses fetchActiveRun fallback after 30s without announcement", async () => {
    const onActiveRun = vi.fn()
    const deps = createDeps({
      fetchActiveRun: vi.fn().mockResolvedValue({
        run_id: "run-timeout",
        topic: "Timeout topic",
      }),
    })

    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: null,
        selectedRunId: "hist-run",
        onActiveRun,
      },
      deps,
    )

    expect(deps.timeouts[0]?.delay).toBe(30_000)
    deps.timeouts[0]?.fn()
    await Promise.resolve()

    expect(onActiveRun).toHaveBeenCalledWith({
      run_id: "run-timeout",
      topic: "Timeout topic",
    })
  })

  it("does not reconnect when already connected to the announced run", () => {
    const onActiveRun = vi.fn()
    const unsubscribe = vi.fn()
    const deps = createDeps({
      subscribeWorkflowActiveRun: vi.fn((_workflowId, callbacks) => {
        deps.subscribeCallbacks.onAnnouncement = callbacks.onAnnouncement
        return unsubscribe
      }),
    })

    createWorkflowActiveRunWatcher(
      {
        workflowId: "wf-1",
        liveRunId: "run-live",
        selectedRunId: "run-live",
        onActiveRun,
      },
      deps,
    )

    deps.subscribeCallbacks.onAnnouncement?.({
      workflow_id: "wf-1",
      run_id: "run-live",
      topic: "Already live",
    })

    expect(onActiveRun).not.toHaveBeenCalled()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })
})
