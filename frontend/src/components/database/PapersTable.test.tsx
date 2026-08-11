import { describe, expect, it } from "vitest"
import { renderToStaticMarkup } from "react-dom/server"
import { PapersTable } from "./PapersTable"
import type { PaperAllRow } from "@/lib/api"

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
})
