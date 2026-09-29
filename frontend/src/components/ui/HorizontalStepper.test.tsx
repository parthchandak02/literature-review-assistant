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

  it("falls back to the last started step label and shows a summary when nothing is current", () => {
    const { rerender } = render(
      <HorizontalStepper
        steps={[
          { key: "a", label: "Alpha", status: "done" },
          { key: "b", label: "Beta", status: "done" },
        ]}
      />,
    )
    expect(screen.getByText("All steps complete")).toBeInTheDocument()
    expect(screen.getByText("Alpha")).toHaveClass("max-sm:sr-only")

    rerender(
      <HorizontalStepper
        steps={[
          { key: "a", label: "Alpha", status: "done" },
          { key: "b", label: "Beta", status: "done" },
          { key: "c", label: "Gamma", status: "pending" },
        ]}
      />,
    )
    expect(screen.queryByText("All steps complete")).not.toBeInTheDocument()
    expect(screen.getByText("Beta")).not.toHaveClass("max-sm:sr-only")
    expect(screen.getByText("Gamma")).toHaveClass("max-sm:sr-only")
  })

  it("does not claim all steps complete when a step was skipped", () => {
    render(
      <HorizontalStepper
        steps={[
          { key: "a", label: "Alpha", status: "done" },
          { key: "b", label: "Beta", status: "skipped" },
          { key: "c", label: "Gamma", status: "done" },
        ]}
      />,
    )
    expect(screen.queryByText("All steps complete")).not.toBeInTheDocument()
    expect(screen.getByText("2 of 3 steps complete · 1 skipped")).toBeInTheDocument()
  })

  it.each(["awaiting", "active", "error"] as const)("shows the %s step label instead of a caption", (status) => {
    render(
      <HorizontalStepper
        steps={[
          { key: "a", label: "Alpha", status: "done" },
          { key: "b", label: "PROSPERO", status },
          { key: "c", label: "Gamma", status: "skipped" },
        ]}
      />,
    )
    expect(screen.queryByText("All steps complete")).not.toBeInTheDocument()
    expect(screen.queryByText(/steps complete/)).not.toBeInTheDocument()
    expect(screen.getByText("PROSPERO")).not.toHaveClass("max-sm:sr-only")
  })
})
