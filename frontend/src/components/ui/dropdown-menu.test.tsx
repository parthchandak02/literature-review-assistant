// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./dropdown-menu"

function Harness({ onSelect }: { onSelect?: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={onSelect}>Resume</DropdownMenuItem>
        <DropdownMenuItem>Archive</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

describe("DropdownMenu", () => {
  it("opens from the keyboard and closes with Escape", async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const trigger = screen.getByRole("button", { name: "Actions" })

    trigger.focus()
    await user.keyboard("{Enter}")
    expect(await screen.findByRole("menu")).toBeInTheDocument()
    expect(screen.getByRole("menuitem", { name: "Resume" })).toBeInTheDocument()

    await user.keyboard("{Escape}")
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it("selects an item with the keyboard", async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<Harness onSelect={onSelect} />)
    screen.getByRole("button", { name: "Actions" }).focus()
    await user.keyboard("{Enter}")
    await screen.findByRole("menu")
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Resume" })).toHaveFocus())
    await user.keyboard("{Enter}")
    expect(onSelect).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument())
  })
})
