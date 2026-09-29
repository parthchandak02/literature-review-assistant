import { describe, expect, it } from "vitest"
import { artifactFileLabel, collectFiles } from "./artifactFileUtils"

describe("artifactFileLabel", () => {
  it.each([
    ["doc_search_strategies_appendix.md", "Search strategies appendix"],
    ["doc_fulltext_retrieval_coverage.md", "Full-text retrieval coverage"],
    ["data_papers_manifest.json", "Papers manifest"],
    ["fig_prisma_flow.png", "PRISMA flow diagram"],
    ["fig_custom_02.png", "Custom diagram 2"],
    ["references.bib", "BibTeX references"],
    ["data_new_llm_report.json", "New LLM report"],
    ["notes.tex", "LaTeX: notes.tex"],
  ])("%s -> %s", (name, expected) => {
    expect(artifactFileLabel(name)).toBe(expected)
  })
})

describe("collectFiles", () => {
  it("keeps the real filename alongside the friendly label", () => {
    const [file] = collectFiles({ artifacts: { search_appendix: "/runs/x/doc_search_strategies_appendix.md" } })
    expect(file.label).toBe("Search strategies appendix")
    expect(file.fileName).toBe("doc_search_strategies_appendix.md")
  })
})
