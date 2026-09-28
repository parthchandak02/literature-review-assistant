// @vitest-environment jsdom
import "@/test/dom"
import { createElement, useEffect, type ReactNode } from "react"
import { describe, expect, it } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { MemoryRouter, useLocation } from "react-router-dom"
import { parseRunUrl } from "@/lib/runSessionUrl"
import {
  EMPTY_PAPERS_QUERY,
  buildFilterChips,
  countActiveFilters,
  nextSort,
  parseDbSearchParams,
  removeFilterById,
  toggleFacetValue,
  useDbFilters,
  writeDbSearchParams,
  type DbTableState,
} from "./useDbFilters"

const baseState: DbTableState = {
  filters: EMPTY_PAPERS_QUERY,
  sort: { sort: null, dir: "desc" },
  page: 0,
  pageSize: 50,
}

describe("URL search param encoding", () => {
  it("round-trips filters, sort, page and size", () => {
    const state: DbTableState = {
      filters: {
        ...EMPTY_PAPERS_QUERY,
        title: "sleep",
        ta: ["include", "__none__"],
        source: ["pubmed"],
        yearMin: 2015,
        yearMax: 2020,
      },
      sort: { sort: "title", dir: "asc" },
      page: 2,
      pageSize: 100,
    }
    const sp = writeDbSearchParams(new URLSearchParams(), state)
    expect(sp.getAll("ta")).toEqual(["include", "__none__"])
    expect(sp.get("page")).toBe("3")
    expect(parseDbSearchParams(sp)).toEqual(state)
  })

  it("omits defaults and keeps params it doesn't own", () => {
    const sp = writeDbSearchParams(new URLSearchParams("foo=1&ta=old"), baseState)
    expect(sp.toString()).toBe("foo=1")
  })

  it("ignores unknown sort keys and page sizes", () => {
    const state = parseDbSearchParams(new URLSearchParams("sort=abstract&size=7&page=-4"))
    expect(state.sort).toEqual({ sort: null, dir: "desc" })
    expect(state.pageSize).toBe(50)
    expect(state.page).toBe(0)
  })
})

describe("nextSort", () => {
  it("cycles unsorted -> asc -> desc -> unsorted", () => {
    const a = nextSort({ sort: null, dir: "desc" }, "title")
    expect(a).toEqual({ sort: "title", dir: "asc" })
    const b = nextSort(a, "title")
    expect(b).toEqual({ sort: "title", dir: "desc" })
    expect(nextSort(b, "title")).toEqual({ sort: null, dir: "desc" })
  })

  it("starts year descending, then ascending, then unsorted", () => {
    const a = nextSort({ sort: null, dir: "desc" }, "year")
    expect(a).toEqual({ sort: "year", dir: "desc" })
    const b = nextSort(a, "year")
    expect(b).toEqual({ sort: "year", dir: "asc" })
    expect(nextSort(b, "year")).toEqual({ sort: null, dir: "desc" })
    expect(nextSort({ sort: "title", dir: "asc" }, "year")).toEqual({ sort: "year", dir: "desc" })
  })

  it("starts ascending when switching column", () => {
    expect(nextSort({ sort: "year", dir: "desc" }, "title")).toEqual({ sort: "title", dir: "asc" })
  })
})

describe("facet helpers", () => {
  it("toggles values in and out", () => {
    expect(toggleFacetValue([], "include")).toEqual(["include"])
    expect(toggleFacetValue(["include", "exclude"], "include")).toEqual(["exclude"])
  })

  it("builds one chip per value and removes by chip id", () => {
    const filters = { ...EMPTY_PAPERS_QUERY, ta: ["include", "__none__"], yearMin: 2019 }
    const chips = buildFilterChips(filters)
    expect(chips.map((c) => c.value)).toEqual(["2019 or later", "Include", "Not screened"])
    expect(countActiveFilters(filters)).toBe(3)
    const next = removeFilterById(filters, "ta:__none__")
    expect(next.ta).toEqual(["include"])
    expect(removeFilterById(next, "year").yearMin).toBeNull()
  })
})

function renderWithRouter(initial: string) {
  const seen = { current: "" }
  function Spy() {
    const loc = useLocation()
    useEffect(() => {
      seen.current = `${loc.pathname}${loc.search}`
    })
    return null
  }
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(MemoryRouter, { initialEntries: [initial] }, children, createElement(Spy))
  const hook = renderHook(() => useDbFilters("run-1"), { wrapper })
  return { ...hook, location: () => seen.current }
}

describe("useDbFilters URL sync", () => {
  it("reads state from a deep link", () => {
    const { result } = renderWithRouter("/run/wf-1/database?ta=include&sort=year&dir=asc&page=2")
    expect(result.current.filters.ta).toEqual(["include"])
    expect(result.current.sort).toEqual({ sort: "year", dir: "asc" })
    expect(result.current.page).toBe(1)
  })

  it("writes changes to the URL, resets page on filter change, and keeps the run path", () => {
    const { result, location } = renderWithRouter("/run/wf-1/database?page=3")
    expect(result.current.page).toBe(2)
    act(() => result.current.toggleFacet("source", "pubmed"))
    expect(result.current.filters.source).toEqual(["pubmed"])
    expect(result.current.page).toBe(0)
    expect(location()).toBe("/run/wf-1/database?src=pubmed")
    expect(parseRunUrl("/run/wf-1/database")).toEqual({ workflowId: "wf-1", tab: "database" })

    act(() => result.current.toggleSort("title"))
    act(() => result.current.setPage(1))
    expect(location()).toBe("/run/wf-1/database?src=pubmed&sort=title&dir=asc&page=2")
  })

  it("does not reset the page when a text filter re-applies the same value", () => {
    const { result } = renderWithRouter("/run/wf-1/database?title=sleep&page=3")
    act(() => result.current.setTitleFilter("sleep"))
    expect(result.current.page).toBe(2)
  })

  it("restores the last view after a tab switch drops the query string", () => {
    const first = renderWithRouter("/run/wf-1/database")
    act(() => first.result.current.toggleFacet("ta", "exclude"))
    first.unmount()

    const second = renderWithRouter("/run/wf-1/database")
    expect(second.result.current.filters.ta).toEqual(["exclude"])
    expect(second.location()).toBe("/run/wf-1/database?ta=exclude")
  })

  it("does not restore after the user clears filters", () => {
    const first = renderWithRouter("/run/wf-1/database?ta=exclude")
    act(() => first.result.current.clearAllFilters())
    first.unmount()
    const second = renderWithRouter("/run/wf-1/database")
    expect(second.result.current.filters.ta).toEqual([])
  })
})
