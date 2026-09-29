// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactElement } from "react"
import type { ReviewEvent } from "@/lib/api"

const fetchDbCostDashboard = vi.fn()

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...actual,
    fetchDbCostDashboard: (...args: unknown[]) => fetchDbCostDashboard(...args),
    fetchHistoricalReviewEvents: vi.fn(async () => []),
  }
})

vi.mock("@/components/LogStream", () => ({
  LogStream: () => <div data-testid="log-stream" />,
}))

import { ActivityView } from "./ActivityView"

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function phase(type: "phase_start" | "phase_done", name: string, ts: string): ReviewEvent {
  return type === "phase_start"
    ? { type, phase: name, description: "", total: null, ts }
    : { type, phase: name, summary: {}, total: null, completed: null, ts }
}

const FAILED_EVENTS: ReviewEvent[] = [
  phase("phase_start", "phase_1_prospero_gate", "2026-03-12T00:00:00Z"),
  phase("phase_done", "phase_1_prospero_gate", "2026-03-12T00:00:01Z"),
  phase("phase_start", "phase_2_search", "2026-03-12T00:00:02Z"),
  phase("phase_done", "phase_2_search", "2026-03-12T00:01:00Z"),
  phase("phase_start", "phase_3_screening", "2026-03-12T00:01:01Z"),
  { type: "error", msg: "Rate limited" },
  { type: "error", msg: "Screening crashed" },
]

const DASHBOARD = {
  by_model: [],
  by_phase: [
    { phase: "phase_2_search", cost_usd: 0.5, calls: 3 },
    { phase: "phase_3_screening", cost_usd: 1.25, calls: 40 },
    { phase: "screening_calibration", cost_usd: 0.25, calls: 4 },
  ],
  totals: { cost_usd: 2, tokens_in: 0, tokens_out: 0, calls: 47 },
}

beforeEach(() => {
  fetchDbCostDashboard.mockReset()
  fetchDbCostDashboard.mockResolvedValue(DASHBOARD)
})

describe("ActivityView failure banner", () => {
  it("shows the last error with role=alert and the failed phase", () => {
    renderWithQuery(
      <ActivityView events={FAILED_EVENTS} status="error" runId="run-1" />,
    )
    const alert = screen.getByRole("alert")
    expect(within(alert).getByText("Run failed in Study screening")).toBeInTheDocument()
    expect(within(alert).getByText("Screening crashed")).toBeInTheDocument()
    expect(within(alert).queryByText("Rate limited")).not.toBeInTheDocument()
    expect(alert).not.toHaveTextContent(/Review failed/)
    expect(within(alert).getByRole("button", { name: "Show in log" })).toBeInTheDocument()
    expect(within(alert).queryByRole("button", { name: /Resume from/ })).not.toBeInTheDocument()
  })

  it("offers resume from the failed phase and confirms before calling the API", async () => {
    const user = userEvent.setup()
    const onResume = vi.fn(async () => {})
    renderWithQuery(
      <ActivityView
        events={FAILED_EVENTS}
        status="idle"
        historicalStatus="failed"
        runId="run-1"
        onResumeFromPhase={onResume}
        resumeModeActive
      />,
    )
    const alert = screen.getByRole("alert")
    await user.click(within(alert).getByRole("button", { name: "Resume from Study screening" }))
    const dialog = await screen.findByRole("dialog")
    expect(within(dialog).getByText("Resume from Study screening?")).toBeInTheDocument()
    expect(onResume).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole("button", { name: "Resume run" }))
    await waitFor(() => expect(onResume).toHaveBeenCalledWith("phase_3_screening"))
  })
})

describe("ActivityView resume menu", () => {
  it("lists resumable phases, disables unreachable ones, and shows re-run phases with prior cost", async () => {
    const user = userEvent.setup()
    const onResume = vi.fn(async () => {})
    renderWithQuery(
      <ActivityView
        events={FAILED_EVENTS}
        status="idle"
        historicalStatus="failed"
        runId="run-1"
        onResumeFromPhase={onResume}
        resumeModeActive
      />,
    )
    await user.click(screen.getByRole("button", { name: /Resume from…/ }))
    const menu = await screen.findByRole("menu")
    expect(within(menu).getByText("Resume from phase")).toBeInTheDocument()
    expect(within(menu).getByRole("group", { name: "Discovery" })).toBeInTheDocument()
    expect(within(menu).getAllByRole("group")).toHaveLength(6)
    expect(within(menu).getByRole("menuitem", { name: "Literature search" })).not.toHaveAttribute("data-disabled")
    expect(within(menu).getByRole("menuitem", { name: "Manuscript writing" })).toHaveAttribute("data-disabled")

    await user.click(within(menu).getByRole("menuitem", { name: "Literature search" }))
    const dialog = await screen.findByRole("dialog")
    const list = within(dialog).getByRole("list", { name: "Phases that will re-run" })
    const items = within(list).getAllByRole("listitem").map((el) => el.textContent)
    expect(items[0]).toBe("Discovery: Literature search, Study screening, Full-text PDF retrieval")
    expect(items).toContain("Finalize: Manuscript audit, Finalize and export")
    expect(items.join(" ")).not.toContain("PROSPERO")
    expect(await within(dialog).findByText("Previously spent on these phases: $2.00.")).toBeInTheDocument()

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }))
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(onResume).not.toHaveBeenCalled()
  })

  it("shows the blocked reason and disables the menu while the run awaits review", () => {
    renderWithQuery(
      <ActivityView
        events={FAILED_EVENTS.slice(0, 5)}
        status="idle"
        historicalStatus="awaiting_review"
        runId="run-1"
        onResumeFromPhase={vi.fn(async () => {})}
        resumeModeActive={false}
      />,
    )
    expect(screen.getByText("Approve screening first before resuming from later phases.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Resume from…/ })).toBeDisabled()
    expect(fetchDbCostDashboard).not.toHaveBeenCalled()
  })

  it("hides resume controls for live runs", () => {
    renderWithQuery(<ActivityView events={FAILED_EVENTS.slice(0, 5)} status="streaming" runId="run-1" />)
    expect(screen.queryByRole("button", { name: /Resume from/ })).not.toBeInTheDocument()
  })
})

describe("ActivityView stepper", () => {
  it("renders an ordered list with aria-current and the live sub-status", () => {
    const events: ReviewEvent[] = [
      phase("phase_start", "phase_1_prospero_gate", "2026-03-12T00:00:00Z"),
      phase("phase_done", "phase_1_prospero_gate", "2026-03-12T00:00:01Z"),
      phase("phase_start", "fulltext_pdf_retrieval", "2026-03-12T00:00:02Z"),
      { type: "progress", phase: "fulltext_pdf_retrieval", current: 34, total: 120, ts: "2026-03-12T00:01:00Z" },
    ]
    renderWithQuery(<ActivityView events={events} status="streaming" runId="run-1" />)
    const list = screen.getByRole("list", { name: "Run progress" })
    expect(list.tagName).toBe("OL")
    const current = list.querySelector('[aria-current="step"]')
    expect(current).toHaveTextContent("Discovery")
    expect(current).toHaveTextContent("in progress")
    expect(current).toHaveTextContent(/PDF retrieval · 34\/120 · \d+(s|m|h)/)
  })

  it("announces a gate as awaiting your review", () => {
    renderWithQuery(
      <ActivityView
        events={FAILED_EVENTS.slice(0, 5)}
        status="idle"
        historicalStatus="awaiting_review"
        runId="run-1"
      />,
    )
    const current = screen.getByRole("list", { name: "Run progress" }).querySelector('[aria-current="step"]')
    expect(current).toHaveTextContent("Discovery, awaiting your review")
  })
})
