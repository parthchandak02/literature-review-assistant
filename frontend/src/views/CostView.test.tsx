// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { CostView } from "./CostView"
import type { CostStats } from "@/hooks/useCostStats"

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    fetchDbCostDashboard: async () => ({
      run_id: "run-1",
      workflow_id: "wf-1",
      total_cost: 0,
      totals: { calls: 0, cost_usd: 0, tokens_in: 0, tokens_out: 0 },
      by_phase: [],
      by_model: [],
      records: [],
      screening_diagnostics: null,
    }),
  }
})

const empty: CostStats = {
  total_cost: 0,
  total_tokens_in: 0,
  total_tokens_out: 0,
  total_calls: 0,
  by_model: [],
  by_phase: [],
}

const stats: CostStats = {
  total_cost: 2,
  total_tokens_in: 12_300_000,
  total_tokens_out: 4_000,
  total_calls: 20,
  by_model: [{ model: "google:gemini-2.5-flash", calls: 20, tokens_in: 12_300_000, tokens_out: 4_000, cost_usd: 2 }],
  by_phase: [
    { phase: "phase_4_extraction", calls: 5, cost_usd: 0.5 },
    { phase: "phase_4_extraction_quality", calls: 15, cost_usd: 1.5 },
  ],
}

function renderView(props: Partial<React.ComponentProps<typeof CostView>>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CostView costStats={empty} {...props} />
    </QueryClientProvider>,
  )
}

describe("CostView", () => {
  it("picks empty copy by run state", () => {
    renderView({ runState: "finished" })
    expect(screen.getByText("This run finished without recording any LLM calls.")).toBeInTheDocument()
  })

  it("shows unit costs, compact tokens, export and a sorted table with totals", async () => {
    const user = userEvent.setup()
    renderView({ costStats: stats, dbRunId: "run-1", includedCount: 10, screenedCount: 2000 })
    expect(await screen.findByText("$0.20 / included study · $1.00 / 1k screened")).toBeInTheDocument()
    expect(screen.getByText("12.3M tokens")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute("href", expect.stringContaining("/db/run-1/costs/export"))
    expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument()

    await user.click(screen.getAllByRole("button", { name: "Table" })[0])
    const phaseTable = screen.getAllByRole("table")[0]
    const rows = within(phaseTable).getAllByRole("row").map((r) => r.textContent)
    expect(rows[1]).toContain("Extraction + quality")
    expect(rows[1]).toContain("75%")
    expect(rows[2]).toContain("25%")
    expect(rows.at(-1)).toContain("Total")
    expect(rows.at(-1)).toContain("100%")
  })
})
