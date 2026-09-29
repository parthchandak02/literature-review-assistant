// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ConfirmDialog } from "./ConfirmDialog"
import { DeleteConfirmDialog } from "./DeleteConfirmDialog"

describe("ConfirmDialog", () => {
  it("shows onConfirm errors inline and stays open", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    const onConfirm = vi.fn(async () => {
      throw new Error("Cannot delete a run that is currently in progress")
    })
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Delete?"
        description="Gone for good."
        confirmLabel="Delete permanently"
        onConfirm={onConfirm}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Delete permanently" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cannot delete a run that is currently in progress",
    )
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Delete permanently" })).toBeEnabled()
  })

  it("has a Close control alongside Cancel", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Archive?"
        description="Moves it to Archived."
        confirmLabel="Archive"
        onConfirm={vi.fn()}
      />,
    )
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Close" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it("closes after a successful confirm", async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    render(
      <ConfirmDialog
        open
        onOpenChange={onOpenChange}
        title="Stop?"
        description="Stops the run."
        confirmLabel="Stop run"
        onConfirm={async () => {}}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Stop run" }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})

describe("DeleteConfirmDialog", () => {
  it("names the review and lists what gets removed", () => {
    render(
      <DeleteConfirmDialog
        open
        onOpenChange={() => {}}
        workflowId="wf-0007"
        topic="What hospital-based and hospital-linked models of geriatric and palliative care improve outcomes?"
        onConfirm={async () => {}}
      />,
    )
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent(/Delete "What hospital-based and hospital-linked models of.*…" \(#7\)\?/)
    expect(dialog).toHaveTextContent(/review database/i)
    expect(dialog).toHaveTextContent(/manuscript/i)
    expect(dialog).toHaveTextContent(/PDFs/)
    expect(dialog).toHaveTextContent(/artifacts/i)
    expect(screen.getByRole("button", { name: "Delete permanently" })).toBeInTheDocument()
  })
})
