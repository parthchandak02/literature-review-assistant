// @vitest-environment jsdom
import "@/test/dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { EMPTY_PAPERS_QUERY } from "@/hooks/useDbFilters"
import { fetchDbTables, type ExtractedTablesResponse } from "@/lib/api/db"
import { OUTCOMES_PAGE_SIZE, OutcomesTable } from "./OutcomesTable"
import { outcomesCaption } from "./outcomeFormat"

const data: ExtractedTablesResponse = {
  total_rows: 120,
  total_papers: 2,
  offset: 0,
  limit: OUTCOMES_PAGE_SIZE,
  filtered: true,
  papers: [
    {
      paper_id: "p1",
      title: "Exercise &amp; mood",
      doi: null,
      extraction_source: "vision",
      outcomes: [{ name: "Depression", effect_size: 0.4, ci_lower: 0.1, ci_upper: 0.7, p_value: 0.01 }],
    },
  ],
}

describe("outcomesCaption", () => {
  it("describes the unfiltered and filtered scopes", () => {
    expect(outcomesCaption(null)).toBe("Quantitative results from every extracted study.")
    expect(outcomesCaption(1)).toBe("Outcomes for 1 filtered paper.")
    expect(outcomesCaption(1234)).toBe(`Outcomes for ${(1234).toLocaleString()} filtered papers.`)
  })
})

describe("OutcomesTable", () => {
  it("shows the filtered caption, the server total and pages through the server", async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    render(
      <OutcomesTable
        data={data}
        page={0}
        onPageChange={onPageChange}
        filteredPaperCount={12}
        error={null}
        onRetry={vi.fn()}
      />,
    )
    expect(screen.getByText("Outcomes for 12 filtered papers.")).toBeInTheDocument()
    expect(screen.getByText("120 outcome rows")).toBeInTheDocument()
    expect(screen.getByText("Exercise & mood")).toBeInTheDocument()
    expect(screen.getByText("Vision")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /next/i }))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })

  it("uses a filter-specific empty state", () => {
    render(
      <OutcomesTable
        data={{ total_rows: 0, papers: [] }}
        page={0}
        onPageChange={vi.fn()}
        filteredPaperCount={3}
        error={null}
        onRetry={vi.fn()}
      />,
    )
    expect(screen.getByText("No extracted outcomes for the filtered papers.")).toBeInTheDocument()
  })
})

describe("fetchDbTables", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubFetch() {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ total_rows: 0, papers: [] })))
    vi.stubGlobal("fetch", fetchMock)
    return fetchMock
  }

  function calledUrl(fetchMock: ReturnType<typeof stubFetch>): string {
    const calls = fetchMock.mock.calls as unknown as Array<[RequestInfo | URL]>
    return String(calls[0][0])
  }

  it("keeps the legacy unparameterised URL", async () => {
    const fetchMock = stubFetch()
    await fetchDbTables("run-1")
    expect(calledUrl(fetchMock)).toMatch(/\/db\/run-1\/tables$/)
  })

  it("sends the Data tab filters and the page window", async () => {
    const fetchMock = stubFetch()
    await fetchDbTables("run-1", { ...EMPTY_PAPERS_QUERY, source: ["pubmed"], yearMin: 2020 }, { offset: 50, limit: 50 })
    const url = new URL(calledUrl(fetchMock), "http://x")
    expect(url.pathname).toMatch(/\/db\/run-1\/tables$/)
    expect(url.searchParams.get("match")).toBe("exact")
    expect(url.searchParams.getAll("source")).toEqual(["pubmed"])
    expect(url.searchParams.get("year_min")).toBe("2020")
    expect(url.searchParams.get("offset")).toBe("50")
    expect(url.searchParams.get("limit")).toBe("50")
  })
})
