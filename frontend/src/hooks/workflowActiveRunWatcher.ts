import { fetchActiveRun } from "@/lib/api/history"
import {
  nextWatcherFallbackDelay,
  WATCHER_FALLBACK_INITIAL_MS,
} from "@/lib/pollingBackoff"
import {
  subscribeWorkflowActiveRun,
  type WorkflowActiveRunEvent,
} from "@/lib/api/runLifecycle"

export const FALLBACK_TIMEOUT_MS = WATCHER_FALLBACK_INITIAL_MS

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
  let fallbackDelayMs = FALLBACK_TIMEOUT_MS

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

  function resetFallbackBackoff() {
    fallbackDelayMs = FALLBACK_TIMEOUT_MS
  }

  function armFallbackTimeout() {
    if (disposed) return
    clearTimeoutIfNeeded()
    const delayMs = fallbackDelayMs
    timeoutId = deps.setTimeout(() => {
      void fallbackFetchActiveRun()
      if (!disposed) {
        fallbackDelayMs = nextWatcherFallbackDelay(fallbackDelayMs)
        armFallbackTimeout()
      }
    }, delayMs)
  }

  function onWindowFocus() {
    resetFallbackBackoff()
    void fallbackFetchActiveRun()
  }

  unsubStream = deps.subscribeWorkflowActiveRun(input.workflowId, {
    onAnnouncement: handleAnnouncement,
    onError: () => {
      resetFallbackBackoff()
      void fallbackFetchActiveRun()
    },
  })

  void fallbackFetchActiveRun()
  armFallbackTimeout()
  deps.addWindowFocusListener(onWindowFocus)

  return { dispose }
}
