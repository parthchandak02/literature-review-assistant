// @vitest-environment jsdom
import "@/test/dom"
import { useState } from "react"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { GlassTabs } from "./glass-tabs"

type Tab = "a" | "b" | "c"

function Harness() {
  const [active, setActive] = useState<Tab>("a")
  return (
    <GlassTabs<Tab>
      items={[
        { id: "a", label: "Alpha" },
        { id: "b", label: "Beta" },
        { id: "c", label: "Gamma" },
      ]}
      activeTab={active}
      onTabChange={setActive}
    />
  )
}

describe("GlassTabs keyboard navigation", () => {
  it("uses roving tabIndex and arrow/Home/End keys", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const alpha = screen.getByRole("tab", { name: "Alpha" })
    const beta = screen.getByRole("tab", { name: "Beta" })
    const gamma = screen.getByRole("tab", { name: "Gamma" })

    expect(alpha).toHaveAttribute("aria-selected", "true")
    expect(alpha).toHaveAttribute("tabindex", "0")
    expect(beta).toHaveAttribute("tabindex", "-1")
    expect(alpha).toHaveAttribute("aria-controls", "tabpanel-a")

    await user.tab()
    expect(alpha).toHaveFocus()

    await user.keyboard("{ArrowRight}")
    expect(beta).toHaveFocus()
    expect(beta).toHaveAttribute("aria-selected", "true")
    expect(alpha).toHaveAttribute("aria-selected", "false")
    expect(beta).toHaveAttribute("tabindex", "0")

    await user.keyboard("{End}")
    expect(gamma).toHaveFocus()
    expect(gamma).toHaveAttribute("aria-selected", "true")

    await user.keyboard("{ArrowRight}")
    expect(alpha).toHaveFocus()

    await user.keyboard("{ArrowLeft}")
    expect(gamma).toHaveFocus()

    await user.keyboard("{Home}")
    expect(alpha).toHaveFocus()
    expect(alpha).toHaveAttribute("aria-selected", "true")
  })
})
