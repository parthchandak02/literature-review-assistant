// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "./sheet"

function Harness({ side }: { side?: "left" | "right" }) {
  return (
    <>
      <button type="button">Outside</button>
      <Sheet>
        <SheetTrigger>Open</SheetTrigger>
        <SheetContent side={side}>
          <SheetTitle>Filters</SheetTitle>
          <SheetDescription>Refine the list</SheetDescription>
          <button type="button">First</button>
          <button type="button">Second</button>
        </SheetContent>
      </Sheet>
    </>
  )
}

describe("Sheet", () => {
  it("traps focus inside the drawer and closes with Escape", async () => {
    const user = userEvent.setup()
    render(<Harness side="left" />)
    const trigger = screen.getByRole("button", { name: "Open" })
    await user.click(trigger)

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveClass("left-0")
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))

    for (let i = 0; i < 5; i++) {
      await user.tab()
      expect(dialog.contains(document.activeElement)).toBe(true)
    }
    await user.tab({ shift: true })
    expect(dialog.contains(document.activeElement)).toBe(true)

    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it("defaults to the right side", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole("button", { name: "Open" }))
    expect(await screen.findByRole("dialog")).toHaveClass("right-0")
  })
})
