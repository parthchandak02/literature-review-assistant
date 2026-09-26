// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ScreeningReviewView } from "./ScreeningReviewView"
import type { ScreeningSummary } from "@/lib/api"

const summary: ScreeningSummary = {
  run_id: "run-1",
  total: 1,
  instructions: "",
  papers: [
    {
      paper_id: "p1",
      title: "Paper One",
      authors: "Doe",
      year: 2024,
      source_database: "pubmed",
      doi: null,
      abstract: null,
      stage: "title_abstract",
      decision: "uncertain",
      reason: null,
      confidence: 0.5,
    },
  ],
}

const fetchScreeningSummary = vi.fn(async () => summary)

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, fetchScreeningSummary: () => fetchScreeningSummary() }
})

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

function renderView(onApprove?: (o: unknown[]) => Promise<void>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ScreeningReviewView runId="run-1" workflowId="wf-1" onApproveAndResume={onApprove} />
    </QueryClientProvider>,
  )
}

describe("ScreeningReviewView", () => {
  beforeEach(() => {
    fetchScreeningSummary.mockClear()
  })

  it("persists overrides across remounts for the same workflow", async () => {
    const user = userEvent.setup()
    const first = renderView()
    await user.click(await screen.findByText("Paper One"))
    await user.click(screen.getByRole("button", { name: "Force Include" }))
    expect(screen.getByText("Override: include")).toBeInTheDocument()
    first.unmount()

    renderView()
    expect(await screen.findByText("Override: include")).toBeInTheDocument()
    expect(screen.getByText(/1 override will be sent/)).toBeInTheDocument()
  })

  it("keeps the list and shows an inline error when approval fails", async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn(async () => {
      throw new Error("Server exploded")
    })
    renderView(onApprove)
    await user.click(await screen.findByText("Paper One"))
    await user.click(screen.getByRole("button", { name: "Force Exclude" }))
    await user.click(screen.getByRole("button", { name: /Approve Screening/ }))

    expect(onApprove).toHaveBeenCalledWith([
      expect.objectContaining({ paper_id: "p1", decision: "exclude" }),
    ])
    expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded")
    expect(screen.getByText("Paper One")).toBeInTheDocument()
    expect(screen.getByText("Override: exclude")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Approve Screening/ })).toBeEnabled()
  })
})
