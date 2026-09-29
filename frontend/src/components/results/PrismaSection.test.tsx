// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { PrismaCountsResponse } from "@/lib/api"
import { PRISMA_STALE_NOTE, PrismaDiagramCard } from "./PrismaSection"

const fetchPrismaCounts = vi.fn<(runId: string) => Promise<PrismaCountsResponse | null>>()

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, fetchPrismaCounts: (runId: string) => fetchPrismaCounts(runId) }
})

function response(figure_stale: boolean | null): PrismaCountsResponse {
  return { workflow_id: "wf-1", live: {} as PrismaCountsResponse["live"], sidecar: figure_stale == null ? null : { version: 1, generated_at: "", figure: "fig_prisma_flow.png", counts: {} as PrismaCountsResponse["live"] }, figure_stale }
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PrismaDiagramCard filePath="fig_prisma_flow.png" runId="run-1" />
    </QueryClientProvider>,
  )
}

describe("PrismaDiagramCard stale note", () => {
  beforeEach(() => fetchPrismaCounts.mockReset())

  it("shows the note when the sidecar differs from live counts", async () => {
    fetchPrismaCounts.mockResolvedValue(response(true))
    renderCard()
    expect(await screen.findByText(PRISMA_STALE_NOTE)).toBeInTheDocument()
  })

  it.each([false, null])("shows nothing when figure_stale is %s", async (stale) => {
    fetchPrismaCounts.mockResolvedValue(response(stale))
    renderCard()
    await waitFor(() => expect(fetchPrismaCounts).toHaveBeenCalledWith("run-1"))
    expect(screen.queryByText(PRISMA_STALE_NOTE)).not.toBeInTheDocument()
  })
})
