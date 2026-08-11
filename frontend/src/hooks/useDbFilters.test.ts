import { describe, expect, it } from "vitest"
import type { DbPapersFilters } from "@/hooks/useDbPapers"
import {
  buildFilterSignature,
  isDbInitialQuery,
  papersPaginationReducer,
  resolveQueryPage,
} from "./useDbFilters"

const emptyFilters: DbPapersFilters = {
  titleFilter: "",
  authorFilter: "",
  taFilter: "",
  ftFilter: "",
  primaryStatusFilter: "",
  yearFilter: "",
  sourceFilter: "",
  countryFilter: "",
}

describe("papersPaginationReducer", () => {
  const baseState = {
    filterSignature: "sig-a",
    runId: "run-1",
    page: 3,
  }

  it("resets page to 0 when filter signature changes", () => {
    const next = papersPaginationReducer(baseState, {
      type: "sync_scope",
      filterSignature: "sig-b",
      runId: "run-1",
    })
    expect(next).toEqual({
      filterSignature: "sig-b",
      runId: "run-1",
      page: 0,
    })
  })

  it("resets page to 0 when run id changes", () => {
    const next = papersPaginationReducer(baseState, {
      type: "sync_scope",
      filterSignature: "sig-a",
      runId: "run-2",
    })
    expect(next).toEqual({
      filterSignature: "sig-a",
      runId: "run-2",
      page: 0,
    })
  })

  it("keeps page when scope is unchanged", () => {
    const next = papersPaginationReducer(baseState, {
      type: "sync_scope",
      filterSignature: "sig-a",
      runId: "run-1",
    })
    expect(next).toBe(baseState)
  })

  it("updates page without resetting filters", () => {
    const next = papersPaginationReducer(baseState, { type: "set_page", page: 5 })
    expect(next).toEqual({ ...baseState, page: 5 })
  })
})

describe("buildFilterSignature", () => {
  it("changes when any filter field changes", () => {
    const base = buildFilterSignature(emptyFilters)
    expect(buildFilterSignature({ ...emptyFilters, titleFilter: "sleep" })).not.toBe(base)
    expect(buildFilterSignature({ ...emptyFilters, yearFilter: "2020" })).not.toBe(base)
    expect(buildFilterSignature({ ...emptyFilters, taFilter: "include" })).not.toBe(base)
  })

  it("is stable for identical filter objects", () => {
    const filters: DbPapersFilters = {
      ...emptyFilters,
      authorFilter: "Smith",
      countryFilter: "US",
    }
    expect(buildFilterSignature(filters)).toBe(buildFilterSignature({ ...filters }))
  })
})

describe("resolveQueryPage", () => {
  const pagination = { filterSignature: "sig-a", runId: "run-1", page: 4 }

  it("returns stored page when scope matches", () => {
    expect(resolveQueryPage(pagination, "sig-a", "run-1")).toBe(4)
  })

  it("returns 0 when filter signature is stale", () => {
    expect(resolveQueryPage(pagination, "sig-b", "run-1")).toBe(0)
  })

  it("returns 0 when run id is stale", () => {
    expect(resolveQueryPage(pagination, "sig-a", "run-2")).toBe(0)
  })
})

describe("isDbInitialQuery", () => {
  it("is true for unfiltered page 0", () => {
    expect(isDbInitialQuery(0, emptyFilters)).toBe(true)
  })

  it("is false when paginated", () => {
    expect(isDbInitialQuery(1, emptyFilters)).toBe(false)
  })

  it("is false when any filter is active", () => {
    expect(isDbInitialQuery(0, { ...emptyFilters, ftFilter: "exclude" })).toBe(false)
  })
})
