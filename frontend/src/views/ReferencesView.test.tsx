// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { PaperReference } from "@/lib/api"
import { ReferencesView } from "./ReferencesView"

const base: Omit<PaperReference, "paper_id" | "title"> = {
  authors: "Smith J",
  year: 2021,
  source_database: null,
  doi: null,
  url: null,
  country: null,
  retrieval_source: "abstract",
  has_file: false,
  file_type: null,
}

const papers: PaperReference[] = [
  { ...base, paper_id: "a", title: "Exercise &amp; mood", has_file: true, file_type: "pdf", doi: "10.1/a" },
  {
    ...base,
    paper_id: "b",
    title: "Yoga for anxiety",
    source_database: "semantic_scholar",
    retrieval_source: "unpaywall_pdf",
  },
]

vi.mock("@/hooks/useReferences", () => ({
  referencesQueryKey: () => ["refs"],
  useReferences: () => ({ data: papers, isLoading: false, isError: false, error: null, refetch: vi.fn() }),
}))

function renderView() {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ReferencesView runId="run-1" workflowId="wf-1" isDone />
    </QueryClientProvider>,
  )
}

describe("ReferencesView", () => {
  it("decodes titles and labels icon actions", () => {
    renderView()
    expect(screen.getByText("Exercise & mood")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Open DOI 10\.1\/a for Exercise & mood/ })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Download PDF of Exercise & mood" })).toBeInTheDocument()
    expect(screen.queryByText("Full text")).toBeNull()
  })

  it("shows humanised source badges and matches them in search", async () => {
    const user = userEvent.setup()
    renderView()
    expect(screen.getByText("Semantic Scholar")).toBeInTheDocument()
    expect(screen.getByText("Unpaywall")).toBeInTheDocument()
    expect(screen.getByText("Abstract only")).toBeInTheDocument()
    expect(screen.queryByText("semantic_scholar")).toBeNull()
    await user.type(screen.getByRole("searchbox", { name: "Search included studies" }), "semantic scholar")
    expect(screen.getByText("1 of 2 shown")).toBeInTheDocument()
  })

  it("filters by search and full text only, and clears", async () => {
    const user = userEvent.setup()
    renderView()
    await user.type(screen.getByRole("searchbox", { name: "Search included studies" }), "yoga")
    expect(screen.queryByText("Exercise & mood")).toBeNull()
    expect(screen.getByText("1 of 2 shown")).toBeInTheDocument()

    const toggle = screen.getByRole("button", { name: /Full text only/ })
    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("No included studies match these filters.")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Clear filters/ }))
    expect(screen.getByText("Exercise & mood")).toBeInTheDocument()
    expect(screen.getByText("Yoga for anxiety")).toBeInTheDocument()
  })
})
