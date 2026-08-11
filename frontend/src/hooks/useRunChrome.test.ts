import { describe, expect, it } from "vitest"
import { computeRunChrome } from "./useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"
import type { CostStats } from "@/hooks/useCostStats"

const EMPTY_COST: CostStats = {
  total_cost: 0,
  total_tokens_in: 0,
  total_tokens_out: 0,
  total_calls: 0,
  by_model: [],
  by_phase: [],
}

function baseRun(overrides: Partial<SelectedRun> = {}): SelectedRun {
  return {
    runId: "run-1",
    workflowId: "wf-1",
    topic: "Test topic",
    dbPath: null,
    isDone: false,
    startedAt: null,
    ...overrides,
  }
}

describe("computeRunChrome", () => {
  it("prefers cancelled over done when historical status is cancelled", () => {
    const vm = computeRunChrome({
      run: baseRun({ isDone: true, historicalStatus: "cancelled" }),
      events: [],
      effectiveEvents: [],
      isViewingLiveRun: false,
      status: "done",
      costStats: EMPTY_COST,
      resolvedHistoricalStatus: "cancelled",
    })

    expect(vm.statusLabel).toBe("Cancelled")
    expect(vm.isCancelled).toBe(true)
    expect(vm.isDone).toBe(true)
  })

  it("maps live stream status to awaiting_prospero for App tab gating", () => {
    const vm = computeRunChrome({
      run: baseRun(),
      events: [],
      effectiveEvents: [],
      isViewingLiveRun: true,
      status: "streaming",
      streamStatus: "streaming",
      costStats: EMPTY_COST,
      prosperoPrepareInProgress: true,
    })

    expect(vm.liveStatus).toBe("awaiting_prospero")
    expect(vm.isAwaitingProspero).toBe(true)
    expect(vm.statusLabel).toBe("PROSPERO Pending")
  })

  it("merges historical DB cost with live SSE cost", () => {
    const vm = computeRunChrome({
      run: baseRun({ historicalCost: 0.3 }),
      events: [],
      effectiveEvents: [],
      isViewingLiveRun: true,
      status: "streaming",
      streamStatus: "streaming",
      costStats: { ...EMPTY_COST, total_cost: 0.016 },
    })

    expect(vm.displayCost).toBeCloseTo(0.316, 3)
  })

  it("does not treat completed historical runs as prospero-pending after final done", () => {
    const vm = computeRunChrome({
      run: baseRun({
        isDone: true,
        papersIncluded: 7,
        historicalStatus: "completed",
      }),
      events: [],
      effectiveEvents: [
        {
          type: "done",
          outputs: { status: "awaiting_prospero", workflow_id: "wf-0108" },
        } as never,
        {
          type: "done",
          outputs: { status: "done", workflow_id: "wf-0108" },
        } as never,
      ],
      isViewingLiveRun: false,
      status: "done",
      costStats: EMPTY_COST,
      resolvedHistoricalStatus: "completed",
    })

    expect(vm.isAwaitingProspero).toBe(false)
    expect(vm.isDone).toBe(true)
    expect(vm.statusLabel).not.toBe("PROSPERO Pending")
  })

  it("overrides funnel included count from run.papersIncluded on done historical runs", () => {
    const vm = computeRunChrome({
      run: baseRun({
        isDone: true,
        papersIncluded: 12,
        historicalStatus: "completed",
      }),
      events: [
        {
          type: "phase_done",
          phase: "phase_3_screening",
          summary: { included: 5 },
        } as never,
      ],
      effectiveEvents: [
        {
          type: "phase_done",
          phase: "phase_3_screening",
          summary: { included: 5 },
        } as never,
      ],
      isViewingLiveRun: false,
      status: "done",
      costStats: EMPTY_COST,
      resolvedHistoricalStatus: "done",
    })

    const included = vm.displayFunnelStages.find((s) => s.key === "included")
    expect(included?.count).toBe(12)
  })
})
