// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fetchWorkflowValidationSummaryWithChecks } from "@/lib/api"
import { ValidationDiagnostics } from "./ValidationDiagnostics"
import { validationStatusStyle } from "./qualityStatus"

const checks = Array.from({ length: 11 }, (_, i) => ({
  phase: i === 10 ? "phase_2_search" : "phase_5c_pre_writing_gate",
  check_name: i === 0 ? "rag_chunk_coverage" : `check_${i}`,
  status: i === 0 ? "error" : i === 1 ? "warn" : "pass",
  severity: "info",
  metric_value: null,
  details: {},
  source_module: i === 0 ? "orchestration.helpers.pre_writing_gate" : null,
  paper_id: null,
  created_at: "",
}))

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
      screening_diagnostics: {
        batch_parse_degraded: 1,
        batch_id_mismatch: 0,
        batch_missing_fallback: 0,
        contract_violation_count: 2,
        fast_path_include: 0,
        fast_path_exclude: 0,
        cross_reviewed: 0,
      },
    }),
    fetchWorkflowValidationSummaryWithChecks: vi.fn(async () => ({
      workflow_id: "wf-1",
      latest_run: {
        validation_run_id: "v1",
        profile: "default",
        status: "warn",
        tool_version: "1",
        summary: {},
        started_at: "",
        completed_at: "",
        error_count: 1,
        warn_count: 1,
        total_checks: 11,
      },
      checks,
    })),
  }
})

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ValidationDiagnostics runId="run-1" workflowId="wf-1" />
    </QueryClientProvider>,
  )
}

describe("ValidationDiagnostics", () => {
  it("previews 8 checks and expands to all", async () => {
    const user = userEvent.setup()
    renderIt()
    expect(await screen.findByText("Latest validation checks (11)")).toBeInTheDocument()
    expect(screen.getAllByRole("listitem")).toHaveLength(8)
    await user.click(screen.getByRole("button", { name: /Show all 11/ }))
    expect(screen.getAllByRole("listitem")).toHaveLength(11)
  })

  it("hides screening internals behind a technical details disclosure", async () => {
    const user = userEvent.setup()
    renderIt()
    const toggle = await screen.findByRole("button", { name: /Technical details/ })
    expect(toggle).toHaveTextContent("3 screening output problems")
    expect(screen.queryByText("Screening replies in the wrong format")).not.toBeInTheDocument()
    await user.click(toggle)
    expect(screen.getByText("Screening replies in the wrong format")).toBeInTheDocument()
    expect(screen.queryByText(/Batch parse degraded|Missing fallback/)).not.toBeInTheDocument()
  })

  it("shows a shared phase once as the group header", async () => {
    vi.mocked(fetchWorkflowValidationSummaryWithChecks).mockResolvedValueOnce({
      workflow_id: "wf-1",
      latest_run: {
        validation_run_id: "v1",
        profile: "pre_writing_gate",
        status: "passed",
        tool_version: "1",
        summary: {},
        started_at: "",
        completed_at: "",
        error_count: 0,
        warn_count: 0,
        total_checks: 2,
      },
      checks: checks.slice(1, 3),
    })
    renderIt()
    expect(await screen.findByText("Pre-writing readiness check (2)")).toBeInTheDocument()
    expect(screen.getByText("Pre-writing validation")).toBeInTheDocument()
    expect(screen.getAllByText(/Pre-writing readiness check/)).toHaveLength(1)
    expect(screen.queryByText(/Pre writing gate/)).not.toBeInTheDocument()
  })

  it("names checks in plain language and moves the raw id and module path to a tooltip", async () => {
    renderIt()
    const name = await screen.findByText("Evidence passages indexed for every included study")
    expect(name.closest("li")).toHaveAttribute("title", "rag_chunk_coverage · orchestration.helpers.pre_writing_gate")
    expect(screen.queryByText(/orchestration\.helpers/)).not.toBeInTheDocument()
  })

  it("maps statuses to badge variants with icons", () => {
    expect(validationStatusStyle("error").variant).toBe("danger")
    expect(validationStatusStyle("warn").variant).toBe("warning")
    expect(validationStatusStyle("pass").variant).toBe("success")
    expect(validationStatusStyle("weird").variant).toBe("neutral")
  })
})
