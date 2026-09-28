// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { PapersTable } from "./PapersTable"
import { emptyColumns, resolveVisibleColumns } from "./paperColumns"
import type { PaperAllRow } from "@/lib/api/db"

function paperRow(overrides: Partial<PaperAllRow> = {}): PaperAllRow {
  return {
    paper_id: "p1",
    title: "Sample Study",
    authors: "A. Author",
    year: 2024,
    source_database: "pubmed",
    doi: "10.1234/example",
    url: null,
    country: "US",
    ta_decision: "include",
    ft_decision: "include",
    primary_study_status: "primary",
    extraction_confidence: null,
    assessment_source: null,
    ...overrides,
  }
}

describe("PapersTable", () => {
  it("renders paper rows without throwing", () => {
    const html = renderToStaticMarkup(<PapersTable papers={[paperRow()]} />)
    expect(html).toContain("Sample Study")
    expect(html).toContain("A. Author")
    expect(html).toContain("https://doi.org/10.1234/example")
  })

  it("decodes entities and exposes full text via title attributes", () => {
    render(<PapersTable papers={[paperRow({ title: "students&amp;apos; sleep" })]} />)
    expect(screen.getByTitle("students' sleep")).toBeInTheDocument()
  })

  it("renders sort buttons with aria-sort and calls onSort", async () => {
    const user = userEvent.setup()
    const onSort = vi.fn()
    render(
      <PapersTable papers={[paperRow()]} sort={{ sort: "year", dir: "asc" }} onSort={onSort} />,
    )
    const yearHeader = screen.getByRole("columnheader", { name: /year/i })
    expect(yearHeader).toHaveAttribute("aria-sort", "ascending")
    expect(screen.getByRole("columnheader", { name: /^title$/i })).toHaveAttribute("aria-sort", "none")

    await user.click(within(yearHeader).getByRole("button"))
    expect(onSort).toHaveBeenCalledWith("year")
    await user.click(screen.getByRole("button", { name: /full-text decision/i }))
    expect(onSort).toHaveBeenLastCalledWith("ft_decision")
  })

  it("merges screening into one cell with stacked badges", () => {
    render(<PapersTable papers={[paperRow({ ft_decision: "exclude" })]} />)
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toContain("Screening")
    expect(screen.getByText("Exclude")).toBeInTheDocument()
    expect(screen.getByText("Primary")).toBeInTheDocument()
  })

  it("opens a paper from the title button", async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<PapersTable papers={[paperRow()]} onOpenPaper={onOpen} />)
    await user.click(screen.getByRole("button", { name: "Sample Study" }))
    expect(onOpen).toHaveBeenCalledWith("p1")
  })
})

describe("column auto-hide", () => {
  const papers = [
    paperRow({ country: null, ft_decision: null }),
    paperRow({ paper_id: "p2", country: "", ft_decision: "include" }),
  ]

  it("hides columns that are empty on every row", () => {
    expect([...emptyColumns(papers)].sort()).toEqual(["confidence", "country", "rob"])
    const visible = resolveVisibleColumns(papers, {})
    expect(visible.has("country")).toBe(false)
    expect(visible.has("screening")).toBe(true)
  })

  it("lets explicit overrides win in both directions", () => {
    const visible = resolveVisibleColumns(papers, { country: true, authors: false })
    expect(visible.has("country")).toBe(true)
    expect(visible.has("authors")).toBe(false)
  })

  it("does not render hidden columns", () => {
    render(<PapersTable papers={papers} visibleColumns={resolveVisibleColumns(papers, {})} />)
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent)
    expect(headers).not.toContain("Country")
    expect(headers).not.toContain("RoB source")
  })
})
