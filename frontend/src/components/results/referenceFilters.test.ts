import { describe, expect, it } from "vitest"
import type { PaperReference } from "@/lib/api"
import { filterReferences, hasFullText } from "./referenceFilters"

function paper(overrides: Partial<PaperReference>): PaperReference {
  return {
    paper_id: "p",
    title: "",
    authors: "",
    year: null,
    source_database: null,
    doi: null,
    url: null,
    country: null,
    retrieval_source: "abstract",
    has_file: false,
    file_type: null,
    ...overrides,
  }
}

const papers = [
  paper({ paper_id: "a", title: "Exercise &amp; depression in adults", authors: "Smith J", year: 2021, has_file: true, file_type: "pdf" }),
  paper({ paper_id: "b", title: "Yoga for anxiety", authors: "Lee K", year: 2019, doi: "10.1/xyz", source_database: "PubMed" }),
  paper({ paper_id: "c", title: "Diet and mood", authors: "Smith A", year: 2020, has_file: true, file_type: null }),
]

const ids = (list: PaperReference[]) => list.map((p) => p.paper_id)

describe("filterReferences", () => {
  it("returns everything with empty filters", () => {
    expect(ids(filterReferences(papers, { query: "", fullTextOnly: false }))).toEqual(["a", "b", "c"])
    expect(ids(filterReferences(papers, { query: "   ", fullTextOnly: false }))).toEqual(["a", "b", "c"])
  })

  it("matches every term across title, authors, year, DOI and database", () => {
    expect(ids(filterReferences(papers, { query: "smith", fullTextOnly: false }))).toEqual(["a", "c"])
    expect(ids(filterReferences(papers, { query: "Smith 2020", fullTextOnly: false }))).toEqual(["c"])
    expect(ids(filterReferences(papers, { query: "10.1/xyz", fullTextOnly: false }))).toEqual(["b"])
    expect(ids(filterReferences(papers, { query: "pubmed", fullTextOnly: false }))).toEqual(["b"])
  })

  it("searches decoded titles", () => {
    expect(ids(filterReferences(papers, { query: "exercise & depression", fullTextOnly: false }))).toEqual(["a"])
    expect(ids(filterReferences(papers, { query: "amp", fullTextOnly: false }))).toEqual([])
  })

  it("keeps only papers with a saved file when full text only is on", () => {
    expect(ids(filterReferences(papers, { query: "", fullTextOnly: true }))).toEqual(["a"])
    expect(ids(filterReferences(papers, { query: "yoga", fullTextOnly: true }))).toEqual([])
  })

  it("requires a file type for full text", () => {
    expect(hasFullText(papers[0])).toBe(true)
    expect(hasFullText(papers[2])).toBe(false)
  })
})
