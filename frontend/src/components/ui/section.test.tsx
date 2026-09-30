// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { CollapsibleSection } from "./section"
import { ViewToolbar } from "./view-toolbar"
import { GlassTabs } from "./glass-tabs"

describe("CollapsibleSection", () => {
  it("exposes aria-expanded and aria-controls on the toggle", async () => {
    const user = userEvent.setup()
    render(
      <CollapsibleSection title="Details">
        <p>Body</p>
      </CollapsibleSection>,
    )
    const toggle = screen.getByRole("button", { name: /Details/ })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    const controls = toggle.getAttribute("aria-controls")
    expect(controls).toBeTruthy()
    expect(document.getElementById(controls!)).not.toBeNull()
    expect(screen.queryByText("Body")).not.toBeInTheDocument()

    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(document.getElementById(controls!)).toContainElement(screen.getByText("Body"))
  })
})

describe("ViewToolbar height", () => {
  it("keeps fixed height by default and drops it for height=auto", () => {
    const { container, rerender } = render(<ViewToolbar title="T" />)
    expect(container.firstChild).toHaveClass("h-11")
    rerender(<ViewToolbar title="T" height="auto" />)
    expect(container.firstChild).not.toHaveClass("h-11")
    expect(container.firstChild).toHaveClass("py-3")
  })

  it("wrap lets the actions drop to their own row instead of shrinking the title", () => {
    const { container } = render(<ViewToolbar wrap title="T" actions={<button type="button">A</button>} />)
    const root = container.firstChild as HTMLElement
    expect(root).toHaveClass("flex-wrap")
    expect(root).not.toHaveClass("h-11")
    const [title, actions] = Array.from(root.children)
    expect(title).toHaveClass("flex-auto")
    expect(actions).toHaveClass("flex-wrap", "min-w-0")
    expect(actions).not.toHaveClass("shrink-0")
  })
})

describe("GlassTabs variants", () => {
  it("renders a focus ring and the underline variant", () => {
    render(
      <GlassTabs
        variant="underline"
        items={[
          { id: "a", label: "Alpha" },
          { id: "b", label: "Beta" },
        ]}
        activeTab="a"
        onTabChange={() => {}}
      />,
    )
    const alpha = screen.getByRole("tab", { name: "Alpha" })
    expect(alpha).toHaveClass("focus-visible:ring-2", "focus-visible:ring-ring", "border-b-2")
    expect(alpha).toHaveClass("border-intent-primary")
    expect(screen.getByRole("tab", { name: "Beta" })).toHaveClass("border-transparent")
  })
})
