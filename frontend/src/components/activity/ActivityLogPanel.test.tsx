// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReviewEvent } from "@/lib/api"
import { ActivityLogPanel, type ActivityLogPanelProps } from "./ActivityLogPanel"

const received: ReviewEvent[][] = []

vi.mock("@/components/LogStream", () => ({
  LogStream: ({ events }: { events: ReviewEvent[] }) => {
    received.push(events)
    return <div data-testid="log-stream">{events.map((e) => e.type).join(",")}</div>
  },
}))

const TS = "2026-03-12T00:00:00Z"
const EVENTS: ReviewEvent[] = [
  { type: "phase_start", phase: "phase_3_screening", description: "", total: null, ts: TS },
  { type: "status", message: "working", ts: TS },
  { type: "warn", message: "careful", ts: TS },
  { type: "error", msg: "boom", ts: TS },
  { type: "screening_decision", paper_id: "p1", stage: "title_abstract", decision: "include", ts: TS },
]

function renderPanel(overrides: Partial<ActivityLogPanelProps> = {}) {
  const props: ActivityLogPanelProps = {
    searchQuery: "",
    onSearchQueryChange: vi.fn(),
    effectiveLoadingHistory: false,
    eventCountLabel: `${EVENTS.length} events`,
    fetchError: null,
    filteredEvents: EVENTS,
    runId: "run-1",
    workflowId: null,
    onRetryHistorical: vi.fn(),
    ...overrides,
  }
  render(<ActivityLogPanel {...props} />)
  return props
}

describe("ActivityLogPanel", () => {
  it("filters by severity chips and updates the count", async () => {
    renderPanel()
    const log = screen.getByTestId("log-stream")
    expect(log).toHaveTextContent("phase_start,status,warn,error,screening_decision")
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true")

    await userEvent.click(screen.getByRole("button", { name: "Warnings+" }))
    expect(screen.getByTestId("log-stream")).toHaveTextContent("phase_start,warn,error")
    expect(screen.getByText("2 of 5 events")).toBeInTheDocument()

    await userEvent.click(screen.getByRole("button", { name: "Errors" }))
    expect(screen.getByTestId("log-stream")).toHaveTextContent("phase_start,error")

    await userEvent.click(screen.getByRole("button", { name: "Decisions" }))
    expect(screen.getByTestId("log-stream")).toHaveTextContent("phase_start,screening_decision")
    expect(screen.getByRole("button", { name: "Decisions" })).toHaveAttribute("aria-pressed", "true")
  })

  it("offers Show all when a severity filter has no matches", async () => {
    renderPanel({ filteredEvents: EVENTS.slice(0, 2) })
    await userEvent.click(screen.getByRole("button", { name: "Errors" }))
    expect(screen.getByText("No errors yet.")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Show all events" }))
    expect(screen.getByTestId("log-stream")).toBeInTheDocument()
  })

  it("shows a no-match message with Clear for an empty search", async () => {
    const props = renderPanel({ searchQuery: "zzz", filteredEvents: [] })
    expect(screen.getByLabelText("Search activity log")).toHaveValue("zzz")
    expect(screen.getByText("No events match ‘zzz’")).toBeInTheDocument()
    expect(screen.queryByText(/Events will appear here/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }))
    expect(props.onSearchQueryChange).toHaveBeenCalledWith("")
  })

  it("shows the waiting copy when there are no events and no search", () => {
    renderPanel({ filteredEvents: [] })
    expect(screen.getByText("Events will appear here once the review starts.")).toBeInTheDocument()
  })
})
