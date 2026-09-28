// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ProsperoGatePanel } from "./ProsperoGatePanel"

describe("ProsperoGatePanel", () => {
  it("shows the CRD format helper and an error on blur", async () => {
    const user = userEvent.setup()
    render(<ProsperoGatePanel runId="r1" mode="gate" onStartResearch={vi.fn()} />)
    const input = screen.getByLabelText("PROSPERO ID")
    expect(screen.getByText(/CRD42 followed by digits/)).toBeInTheDocument()

    await user.type(input, "CRD-123")
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    await user.tab()
    expect(screen.getByRole("alert")).toHaveTextContent(/digits only/)
    expect(input).toHaveAttribute("aria-invalid", "true")

    await user.clear(input)
    await user.type(input, "CRD42025678901")
    await user.tab()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("tells scoping reviews registration is required and keeps skip hidden until the backend supports it", () => {
    render(
      <ProsperoGatePanel
        runId="r1"
        mode="gate"
        reviewType="scoping"
        onStartResearch={vi.fn()}
        onStartWithoutRegistration={vi.fn()}
      />,
    )
    expect(screen.getByText("PROSPERO registration")).toBeInTheDocument()
    expect(screen.getByText(/Registration is required before search starts/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Start without registration" })).not.toBeInTheDocument()
  })
})
