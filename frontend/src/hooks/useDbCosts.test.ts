import { describe, expect, it } from "vitest"
import { dbCostAggregatesQueryKey } from "./useDbCosts"

describe("dbCostAggregatesQueryKey", () => {
  it("includes granularity so cache keys differ by bucket size", () => {
    expect(dbCostAggregatesQueryKey("run-1", "2026-01-01", "2026-01-31", "day")).toEqual([
      "dbCostAggregates",
      "run-1",
      "2026-01-01",
      "2026-01-31",
      "day",
    ])
    expect(dbCostAggregatesQueryKey("run-1", "2026-01-01", "2026-01-31", "week")).toEqual([
      "dbCostAggregates",
      "run-1",
      "2026-01-01",
      "2026-01-31",
      "week",
    ])
    expect(
      dbCostAggregatesQueryKey("run-1", "2026-01-01", "2026-01-31", "day"),
    ).not.toEqual(dbCostAggregatesQueryKey("run-1", "2026-01-01", "2026-01-31", "month"))
  })

  it("defaults granularity to day", () => {
    expect(dbCostAggregatesQueryKey("run-1", "", "")).toEqual([
      "dbCostAggregates",
      "run-1",
      "",
      "",
      "day",
    ])
  })
})
