import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { subscribeWorkflowActiveRun } from "@/lib/api/runLifecycle"

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  emitError() {
    this.onerror?.()
  }
}

describe("subscribeWorkflowActiveRun", () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal("EventSource", MockEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("opens workflow SSE stream for the workflow id", () => {
    subscribeWorkflowActiveRun("wf-123", { onAnnouncement: vi.fn() })
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0]?.url).toBe("/api/stream/workflow/wf-123")
  })

  it("calls onAnnouncement when run_id is present", () => {
    const onAnnouncement = vi.fn()
    subscribeWorkflowActiveRun("wf-123", { onAnnouncement })
    MockEventSource.instances[0]?.emitMessage({
      workflow_id: "wf-123",
      run_id: "run-abc",
      topic: "Test topic",
    })
    expect(onAnnouncement).toHaveBeenCalledWith({
      workflow_id: "wf-123",
      run_id: "run-abc",
      topic: "Test topic",
    })
  })

  it("ignores malformed and heartbeat payloads without run_id", () => {
    const onAnnouncement = vi.fn()
    subscribeWorkflowActiveRun("wf-123", { onAnnouncement })
    const es = MockEventSource.instances[0]
    es?.onmessage?.({ data: "not-json" } as MessageEvent)
    es?.emitMessage({})
    expect(onAnnouncement).not.toHaveBeenCalled()
  })

  it("calls onError and closes on unsubscribe", () => {
    const onError = vi.fn()
    const onAnnouncement = vi.fn()
    const unsubscribe = subscribeWorkflowActiveRun("wf-123", { onAnnouncement, onError })
    const es = MockEventSource.instances[0]
    es?.emitError()
    expect(onError).toHaveBeenCalledTimes(1)
    unsubscribe()
    expect(es?.closed).toBe(true)
  })
})
