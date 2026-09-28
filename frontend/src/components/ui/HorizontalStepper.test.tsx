// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { HorizontalStepper } from "./HorizontalStepper"

describe("HorizontalStepper", () => {
  it("fills connectors only for completed segments and marks the current step", () => {
    render(
      <HorizontalStepper
        aria-label="Steps"
        steps={[
          { key: "a", label: "A", status: "done" },
          { key: "b", label: "B", status: "active", subStatus: "Search · 3/9 · 2m" },
          { key: "c", label: "C", status: "pending" },
        ]}
      />,
    )
    const connectors = screen.getAllByTestId("stepper-connector")
    expect(connectors.map((c) => c.getAttribute("data-filled"))).toEqual(["true", "false"])
    const items = screen.getAllByRole("listitem")
    expect(items[1]).toHaveAttribute("aria-current", "step")
    expect(items[0]).not.toHaveAttribute("aria-current")
    expect(items[0]).toHaveTextContent("A, complete")
    expect(items[2]).toHaveTextContent("C, not started")
    expect(screen.getByText("Search · 3/9 · 2m")).toBeInTheDocument()
  })
})
