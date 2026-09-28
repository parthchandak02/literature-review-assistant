// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { FetchError } from "./feedback"

describe("FetchError", () => {
  it("shows only the message when no handlers are passed", () => {
    render(<FetchError message="Boom" />)
    expect(screen.getByRole("alert")).toHaveTextContent("Boom")
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("labels onRetry as Retry", async () => {
    const onRetry = vi.fn()
    render(<FetchError message="Boom" onRetry={onRetry} />)
    await userEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(onRetry).toHaveBeenCalledOnce()
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument()
  })

  it("labels onDismiss as Dismiss", async () => {
    const onDismiss = vi.fn()
    render(<FetchError message="Boom" onDismiss={onDismiss} />)
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(onDismiss).toHaveBeenCalledOnce()
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument()
  })

  it("renders both actions when both handlers are passed", async () => {
    const onRetry = vi.fn()
    const onDismiss = vi.fn()
    render(<FetchError message="Boom" onRetry={onRetry} onDismiss={onDismiss} />)
    await userEvent.click(screen.getByRole("button", { name: "Retry" }))
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }))
    expect(onRetry).toHaveBeenCalledOnce()
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})
