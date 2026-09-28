// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ValidationDiagnostics, validationStatusStyle } from "./ValidationDiagnostics"

const checks = Array.from({ length: 11 }, (_, i) => ({
  phase: "phase_2_search",
  check_name: `check_${i}`,
  status: i === 0 ? "error" : i === 1 ? "warn" : "pass",
  severity: "info",
  metric_value: null,
  details: {},
  source_module: null,
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
    fetchWorkflowValidationSummaryWithChecks: async () => ({
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
    }),
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
    expect(await screen.findByText("Contract violations")).toBeInTheDocument()
  })

  it("maps statuses to badge variants with icons", () => {
    expect(validationStatusStyle("error").variant).toBe("danger")
    expect(validationStatusStyle("warn").variant).toBe("warning")
    expect(validationStatusStyle("pass").variant).toBe("success")
    expect(validationStatusStyle("weird").variant).toBe("neutral")
  })
})
