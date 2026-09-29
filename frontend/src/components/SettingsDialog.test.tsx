// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { SettingsDialog } from "./SettingsDialog"

vi.mock("@/components/ApiKeysSection", () => ({
  ApiKeysPanel: () => <div data-testid="keys-panel" />,
}))
vi.mock("@/components/CostsPanel", () => ({
  CostsPanel: () => <div data-testid="costs-panel" />,
}))

describe("SettingsDialog", () => {
  it("renders ARIA tabs and switches with arrow keys", async () => {
    render(<SettingsDialog open onOpenChange={() => {}} />)
    const keysTab = screen.getByRole("tab", { name: "API keys" })
    expect(keysTab).toHaveAttribute("aria-selected", "true")
    expect(screen.getByRole("tabpanel")).toContainElement(screen.getByTestId("keys-panel"))

    keysTab.focus()
    fireEvent.keyDown(keysTab, { key: "ArrowRight" })
    expect(screen.getByRole("tab", { name: "Global costs" })).toHaveAttribute("aria-selected", "true")
    expect(await screen.findByTestId("costs-panel")).toBeInTheDocument()
  })

  it("resets to initialTab every time it opens", async () => {
    const { rerender } = render(<SettingsDialog open onOpenChange={() => {}} initialTab="costs" />)
    expect(screen.getByRole("tab", { name: "Global costs" })).toHaveAttribute("aria-selected", "true")

    await userEvent.click(screen.getByRole("tab", { name: "API keys" }))
    expect(screen.getByTestId("keys-panel")).toBeInTheDocument()

    rerender(<SettingsDialog open={false} onOpenChange={() => {}} initialTab="costs" />)
    rerender(<SettingsDialog open onOpenChange={() => {}} initialTab="costs" />)
    expect(screen.getByRole("tab", { name: "Global costs" })).toHaveAttribute("aria-selected", "true")
    expect(await screen.findByTestId("costs-panel")).toBeInTheDocument()
  })

  it("keeps one dialog width across tabs", async () => {
    render(<SettingsDialog open onOpenChange={() => {}} />)
    const dialog = screen.getByRole("dialog")
    const keysClass = dialog.className
    expect(keysClass).toContain("max-w-4xl")
    await userEvent.click(screen.getByRole("tab", { name: "Global costs" }))
    expect(dialog.className).toBe(keysClass)
  })
})
