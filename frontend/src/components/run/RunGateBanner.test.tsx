// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { RunGateBanner } from "./RunGateBanner"

describe("RunGateBanner", () => {
  it("shows the review gate on other tabs and routes to the review tab", async () => {
    const onTabChange = vi.fn()
    render(<RunGateBanner gate="awaiting_review" activeTab="activity" onTabChange={onTabChange} />)
    expect(screen.getByRole("status")).toHaveTextContent("screening decisions need your approval")
    await userEvent.setup().click(screen.getByRole("button", { name: /Review now/ }))
    expect(onTabChange).toHaveBeenCalledWith("review-screening")
  })

  it("routes config gates to Config", async () => {
    const onTabChange = vi.fn()
    render(<RunGateBanner gate="config_ready" activeTab="cost" onTabChange={onTabChange} />)
    await userEvent.setup().click(screen.getByRole("button", { name: /Open config/ }))
    expect(onTabChange).toHaveBeenCalledWith("config")
  })

  it("is hidden on the action tab and without a gate", () => {
    const { rerender } = render(
      <RunGateBanner gate="awaiting_prospero" activeTab="config" onTabChange={() => {}} />,
    )
    expect(screen.queryByRole("status")).toBeNull()
    rerender(<RunGateBanner gate={null} activeTab="activity" onTabChange={() => {}} />)
    expect(screen.queryByRole("status")).toBeNull()
  })

  it("includes a count when provided", () => {
    render(
      <RunGateBanner gate="awaiting_review" activeTab="activity" onTabChange={() => {}} count={312} />,
    )
    expect(screen.getByRole("status")).toHaveTextContent("(312)")
  })
})
