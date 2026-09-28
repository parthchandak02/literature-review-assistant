// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { SettingsProvider, useSettings } from "./SettingsContext"

vi.mock("@/components/SettingsDialog", () => ({
  SettingsDialog: ({
    open,
    initialTab,
    onOpenChange,
  }: {
    open: boolean
    initialTab: string
    onOpenChange: (open: boolean) => void
  }) =>
    open ? (
      <div role="dialog" data-tab={initialTab}>
        <button type="button" onClick={() => onOpenChange(false)}>
          Close
        </button>
      </div>
    ) : null,
}))

function Opener() {
  const { openSettings, closedVersion } = useSettings()
  return (
    <div>
      <button type="button" onClick={() => openSettings()}>Open default</button>
      <button type="button" onClick={() => openSettings("costs")}>Open costs</button>
      <output aria-label="closed version">{closedVersion}</output>
    </div>
  )
}

describe("SettingsProvider", () => {
  it("does not mount the dialog until first open", () => {
    render(
      <SettingsProvider>
        <Opener />
      </SettingsProvider>,
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("opens on the requested tab, defaulting to keys", async () => {
    const user = userEvent.setup()
    render(
      <SettingsProvider>
        <Opener />
      </SettingsProvider>,
    )
    await user.click(screen.getByRole("button", { name: "Open default" }))
    expect(await screen.findByRole("dialog")).toHaveAttribute("data-tab", "keys")
    await user.click(screen.getByRole("button", { name: "Close" }))
    await user.click(screen.getByRole("button", { name: "Open costs" }))
    expect(await screen.findByRole("dialog")).toHaveAttribute("data-tab", "costs")
  })

  it("bumps closedVersion each time the dialog closes", async () => {
    const user = userEvent.setup()
    render(
      <SettingsProvider>
        <Opener />
      </SettingsProvider>,
    )
    const version = screen.getByLabelText("closed version")
    expect(version).toHaveTextContent("0")
    await user.click(screen.getByRole("button", { name: "Open default" }))
    await user.click(await screen.findByRole("button", { name: "Close" }))
    expect(version).toHaveTextContent("1")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("is a safe no-op outside a provider", async () => {
    const user = userEvent.setup()
    render(<Opener />)
    await user.click(screen.getByRole("button", { name: "Open default" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })
})
