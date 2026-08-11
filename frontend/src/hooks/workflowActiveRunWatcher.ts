import { fetchActiveRun } from "@/lib/api/history"
import {
  subscribeWorkflowActiveRun,
  type WorkflowActiveRunEvent,
} from "@/lib/api/runLifecycle"

const FALLBACK_TIMEOUT_MS = 30_000

export interface WorkflowActiveRunWatcherInput {
  workflowId: string
  liveRunId: string | null
  selectedRunId: string | undefined
  onActiveRun: (event: Pick<WorkflowActiveRunEvent, "run_id" | "topic">) => void
}

export interface WorkflowActiveRunWatcher {
  dispose: () => void
}

type FetchActiveRun = typeof fetchActiveRun
type SubscribeWorkflowActiveRun = typeof subscribeWorkflowActiveRun

export interface WorkflowActiveRunWatcherDeps {
  fetchActiveRun: FetchActiveRun
  subscribeWorkflowActiveRun: SubscribeWorkflowActiveRun
  addWindowFocusListener: (listener: () => void) => void
  removeWindowFocusListener: (listener: () => void) => void
  setTimeout: typeof globalThis.setTimeout
  clearTimeout: typeof globalThis.clearTimeout
}

const defaultDeps: WorkflowActiveRunWatcherDeps = {
  fetchActiveRun,
  subscribeWorkflowActiveRun,
  addWindowFocusListener: (listener) => window.addEventListener("focus", listener),
  removeWindowFocusListener: (listener) => window.removeEventListener("focus", listener),
  setTimeout: globalThis.setTimeout.bind(globalThis),
  clearTimeout: globalThis.clearTimeout.bind(globalThis),
}

export function createWorkflowActiveRunWatcher(
  input: WorkflowActiveRunWatcherInput,
  deps: WorkflowActiveRunWatcherDeps = defaultDeps,
): WorkflowActiveRunWatcher {
  let disposed = false
  let unsubStream: (() => void) | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  function clearTimeoutIfNeeded() {
    if (timeoutId != null) {
      deps.clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  function dispose() {
    if (disposed) return
    disposed = true
    unsubStream?.()
    unsubStream = null
    clearTimeoutIfNeeded()
    deps.removeWindowFocusListener(onWindowFocus)
  }

  function isAlreadyConnected(runId: string): boolean {
    return input.liveRunId === runId && input.selectedRunId === runId
  }

  function handleAnnouncement(event: WorkflowActiveRunEvent) {
    if (disposed) return
    if (isAlreadyConnected(event.run_id)) {
      dispose()
      return
    }
    dispose()
    input.onActiveRun({ run_id: event.run_id, topic: event.topic })
  }

  async function fallbackFetchActiveRun() {
    if (disposed) return
    const res = await deps.fetchActiveRun(input.workflowId)
    if (!res || disposed) return
    handleAnnouncement({
      workflow_id: input.workflowId,
      run_id: res.run_id,
      topic: res.topic,
    })
  }

  function armFallbackTimeout() {
    if (disposed) return
    clearTimeoutIfNeeded()
    timeoutId = deps.setTimeout(() => {
      void fallbackFetchActiveRun()
      if (!disposed) armFallbackTimeout()
    }, FALLBACK_TIMEOUT_MS)
  }

  function onWindowFocus() {
    void fallbackFetchActiveRun()
  }

  unsubStream = deps.subscribeWorkflowActiveRun(input.workflowId, {
    onAnnouncement: handleAnnouncement,
    onError: () => {
      void fallbackFetchActiveRun()
    },
  })

  void fallbackFetchActiveRun()
  armFallbackTimeout()
  deps.addWindowFocusListener(onWindowFocus)

  return { dispose }
}
