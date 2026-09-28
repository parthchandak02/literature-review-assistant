// @vitest-environment jsdom
import "@/test/dom"
import { afterAll, beforeAll, describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { LogStream } from "./LogStream"
import type { ReviewEvent } from "@/lib/api"

const TS = "2026-03-12T00:00:00Z"

const originalHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight")
const originalWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetWidth")

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get: () => 480 })
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 800 })
})

afterAll(() => {
  if (originalHeight) Object.defineProperty(HTMLElement.prototype, "offsetHeight", originalHeight)
  if (originalWidth) Object.defineProperty(HTMLElement.prototype, "offsetWidth", originalWidth)
})

describe("LogStream rendering", () => {
  it("renders readable tags with glossary tooltips and no firehose live region", () => {
    render(
      <LogStream
        events={[
          { type: "phase_start", phase: "phase_2_search", description: "", total: null, ts: TS },
          { type: "progress", phase: "phase_2_search", current: 1, total: 4, ts: TS },
        ]}
      />,
    )
    const log = screen.getByRole("log", { name: "Event log" })
    expect(log).toHaveAttribute("aria-live", "off")
    const tag = screen.getByText("Progress")
    expect(tag).toHaveAttribute("title", "Items processed so far in the current phase.")
    expect(screen.getByText("Search: 1/4")).toBeInTheDocument()
    expect(screen.getByRole("status")).toBeInTheDocument()
  })

  it("keeps decision rows in the grid with their timestamp and expands long reasons", async () => {
    const events: ReviewEvent[] = [
      {
        type: "screening_decision",
        paper_id: "p1",
        stage: "title_abstract",
        decision: "exclude",
        method: "heuristic",
        title: "Paper",
        reason: "custom",
        reason_label: "r".repeat(120),
        ts: TS,
      },
    ]
    render(<LogStream events={events} />)
    expect(screen.getByText("Excluded")).toBeInTheDocument()
    expect(screen.getByText("Rule-based")).toBeInTheDocument()
    expect(screen.getByText(/^\[\d{2}:\d{2}:\d{2}\]$/)).toBeInTheDocument()

    const toggle = screen.getByRole("button", { name: "Show more" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    await userEvent.click(toggle)
    expect(screen.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText(`Reason: ${"r".repeat(120)}`)).toBeInTheDocument()
  })
})
