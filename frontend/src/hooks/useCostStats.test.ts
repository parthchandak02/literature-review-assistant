import { describe, expect, it } from "vitest"
import { aggregateCostStatsFromEvents, buildCostStatsFromDashboard } from "./useCostStats"
import type { CostDashboardResponse } from "@/lib/api"

function dashboardFixture(
  overrides: Partial<CostDashboardResponse> = {},
): CostDashboardResponse {
  return {
    run_id: "run-1",
    workflow_id: "wf-1",
    total_cost: 1.5,
    totals: {
      cost_usd: 1.5,
      tokens_in: 1000,
      tokens_out: 500,
      calls: 10,
    },
    by_model: [
      { model: "gpt-4", calls: 3, tokens_in: 300, tokens_out: 150, cost_usd: 0.5 },
      { model: "claude-3", calls: 7, tokens_in: 700, tokens_out: 350, cost_usd: 1.0 },
    ],
    by_phase: [
      { phase: "phase_2_search", calls: 4, tokens_in: 200, tokens_out: 100, cost_usd: 0.2 },
      { phase: "phase_3_screening", calls: 6, tokens_in: 300, tokens_out: 150, cost_usd: 1.3 },
    ],
    records: [],
    screening_diagnostics: {
      batch_parse_degraded: 0,
      batch_id_mismatch: 0,
      batch_missing_fallback: 0,
      contract_violation_count: 0,
      fast_path_include: 0,
      fast_path_exclude: 0,
      cross_reviewed: 0,
    },
    ...overrides,
  }
}

describe("buildCostStatsFromDashboard", () => {
  it("maps totals and prefers total_cost over totals.cost_usd", () => {
    const stats = buildCostStatsFromDashboard(
      dashboardFixture({
        total_cost: 2.0,
        totals: { ...dashboardFixture().totals, cost_usd: 1.5 },
      }),
    )
    expect(stats.total_cost).toBe(2.0)
    expect(stats.total_tokens_in).toBe(1000)
    expect(stats.total_calls).toBe(10)
  })

  it("sorts by_model and by_phase by cost_usd descending", () => {
    const stats = buildCostStatsFromDashboard(dashboardFixture())
    expect(stats.by_model.map((m) => m.model)).toEqual(["claude-3", "gpt-4"])
    expect(stats.by_phase.map((p) => p.phase)).toEqual(["phase_3_screening", "phase_2_search"])
  })
})

describe("aggregateCostStatsFromEvents", () => {
  it("ignores non-success and non-api_call events", () => {
    const stats = aggregateCostStatsFromEvents([
      { type: "phase_start", phase: "phase_2_search" } as never,
      { type: "api_call", status: "error", cost_usd: 1, model: "m", phase: "p" } as never,
      {
        type: "api_call",
        status: "success",
        cost_usd: 0.1,
        tokens_in: 10,
        tokens_out: 5,
        model: "gpt-4",
        phase: "phase_2_search",
      } as never,
    ])

    expect(stats.total_cost).toBeCloseTo(0.1)
    expect(stats.total_calls).toBe(1)
    expect(stats.by_model[0]?.model).toBe("gpt-4")
    expect(stats.by_phase[0]?.phase).toBe("phase_2_search")
  })
})
