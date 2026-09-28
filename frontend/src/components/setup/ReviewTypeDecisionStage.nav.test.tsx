// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReviewTypeDecisionStage } from "./ReviewTypeDecisionStage"
import { decisionStepPosition, formatDecisionStepPosition } from "./reviewTypeDecisionLogic"

describe("ReviewTypeDecisionStage navigation", () => {
  it("shows a step counter and goes back to the previous question", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ReviewTypeDecisionStage onComplete={vi.fn()} onCancel={onCancel} />)

    expect(screen.getByText("Step 1 of up to 3")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "No" }))
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument()
    expect(screen.getByText("Is it focused on a treatment, exposure, diagnosis, or outcome?")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Yes" }))
    expect(screen.getByText("Step 3 of 3")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(screen.getByText("Is your research question broad?")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Back" }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("does not use the IEDO acronym in visible copy", () => {
    render(<ReviewTypeDecisionStage onComplete={vi.fn()} />)
    expect(document.body.textContent).not.toMatch(/IEDO/)
  })

  it("completes with the resolved type", async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<ReviewTypeDecisionStage onComplete={onComplete} />)
    await user.click(screen.getByRole("button", { name: "Yes" }))
    expect(screen.getByText("Step 2 of 2")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "No" }))
    expect(onComplete).toHaveBeenCalledWith("systematic")
  })

  it("formats the recommendation step without a counter", () => {
    expect(formatDecisionStepPosition(decisionStepPosition("unsure_pick"))).toBe("Recommendation")
  })
})
