import { describe, expect, it } from "vitest"
import { computeRunChrome } from "./useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"
import type { CostStats } from "@/hooks/useCostStats"
import type { PrismaLiveCounts, ReviewEvent } from "@/lib/api"

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
    expect(vm.statusLabel).toBe("PROSPERO pending")
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
    expect(vm.statusLabel).not.toBe("PROSPERO pending")
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

describe("computeRunChrome funnel source", () => {
  const prismaCounts: PrismaLiveCounts = {
    total_identified_databases: 1715,
    total_identified_other: 0,
    duplicates_removed: 167,
    records_after_deduplication: 1548,
    automation_excluded: 1339,
    automation_breakdown: { metadata_filter: 17, rule_prefilter: 493, keyword_ranking: 818, batch_preranker: 11 },
    records_screened: 209,
    records_excluded_screening: 152,
    reports_sought: 57,
    reports_not_retrieved: 50,
    reports_assessed: 7,
    reports_excluded_with_reasons: { wrong_intervention: 1 },
    total_included: 6,
    arithmetic_valid: true,
  }
  const staleEvents = [
    {
      type: "phase_done",
      phase: "phase_2_search",
      summary: { papers: 1548, total_records: 1715, dedup: 167 },
      total: null,
      completed: null,
      ts: "",
    },
    { type: "batch_screen_done", excluded: 11, ts: "" },
  ] as unknown as ReviewEvent[]

  it("uses backend PRISMA counts for a completed run", () => {
    const vm = computeRunChrome({
      run: baseRun({ isDone: true }),
      events: [],
      effectiveEvents: staleEvents,
      isViewingLiveRun: false,
      status: "done",
      costStats: EMPTY_COST,
      prismaCounts,
    })
    expect(vm.displayFunnelStages.map((s) => [s.key, s.count])).toEqual([
      ["identified", 1715],
      ["duplicates", 167],
      ["automation", 1339],
      ["screened", 209],
      ["excluded_ta", 152],
      ["sought", 57],
      ["not_retrieved", 50],
      ["assessed", 7],
      ["excluded_ft", 1],
      ["included", 6],
    ])
  })

  it("keeps the event-based funnel while the run is live", () => {
    const vm = computeRunChrome({
      run: baseRun(),
      events: staleEvents,
      effectiveEvents: staleEvents,
      isViewingLiveRun: true,
      status: "streaming",
      costStats: EMPTY_COST,
      prismaCounts,
    })
    expect(vm.displayFunnelStages.find((s) => s.key === "automation")?.count).toBe(11)
    expect(vm.displayFunnelStages.find((s) => s.key === "screened")?.count).toBe(1537)
  })
})

describe("computeRunChrome stalled config generation", () => {
  const created = "2026-01-01T00:00:00Z"
  const late = Date.parse(created) + 2 * 60 * 60 * 1000
  const input = {
    events: [],
    effectiveEvents: [],
    status: "config_generating",
    costStats: EMPTY_COST,
    now: late,
  }

  it("reads Stalled in the header with no live stream", () => {
    const vm = computeRunChrome({
      ...input,
      run: baseRun({ historicalStatus: "config_generating", createdAt: created }),
      isViewingLiveRun: false,
    })
    expect(vm.isConfigStalled).toBe(true)
    expect(vm.statusLabel).toBe("Stalled")
    expect(vm.gate).toBe("config_stalled")
  })

  it("is not stalled while a config stream is active", () => {
    const vm = computeRunChrome({
      ...input,
      run: baseRun({ historicalStatus: "config_generating", createdAt: created }),
      isViewingLiveRun: false,
      configStreamActive: true,
    })
    expect(vm.isConfigStalled).toBe(false)
    expect(vm.statusLabel).toBe("Generating config")
    expect(vm.gate).toBe("config_generating")
  })
})

describe("computeRunChrome hasScreeningDecisions", () => {
  const base = {
    events: [],
    isViewingLiveRun: false,
    status: "done",
    costStats: EMPTY_COST,
  }

  it("is false before screening and true once screening finished", () => {
    expect(computeRunChrome({ ...base, run: baseRun(), effectiveEvents: [] }).hasScreeningDecisions).toBe(false)
    const done = [{ type: "phase_done", phase: "phase_3_screening" }] as unknown as ReviewEvent[]
    expect(computeRunChrome({ ...base, run: baseRun(), effectiveEvents: done }).hasScreeningDecisions).toBe(true)
  })

  it("is true at the review gate", () => {
    const vm = computeRunChrome({ ...base, run: baseRun({ historicalStatus: "awaiting_review" }), effectiveEvents: [] })
    expect(vm.hasScreeningDecisions).toBe(true)
  })
})
