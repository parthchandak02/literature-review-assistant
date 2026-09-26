// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { RunNavCard } from "./RunNavCard"
import { buildRunCardModel } from "./historyRowModel"

function renderLiveCard(onCancel: () => Promise<void>) {
  const model = buildRunCardModel({
    source: "live",
    liveRun: { runId: "run-1", topic: "Topic", status: "streaming", cost: 0, workflowId: "wf-1" },
    isSelected: true,
    isRunning: true,
  })
  return render(
    <RunNavCard
      model={model}
      collapsed={false}
      wfIdCopied={null}
      onCopyWorkflowId={async () => {}}
      onCancel={onCancel}
    />,
  )
}

describe("RunNavCard stop confirmation", () => {
  it("asks for confirmation before stopping", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn(async () => {})
    renderLiveCard(onCancel)

    await user.click(screen.getByRole("button", { name: "Stop run" }))
    expect(onCancel).not.toHaveBeenCalled()

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent(/resume it later from its last checkpoint/i)

    await user.click(screen.getByRole("button", { name: "Keep running" }))
    expect(onCancel).not.toHaveBeenCalled()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Stop run" }))
    const confirm = await screen.findByRole("dialog")
    const buttons = confirm.querySelectorAll("button")
    const stopButton = Array.from(buttons).find((b) => b.textContent === "Stop run")
    expect(stopButton).toBeDefined()
    await user.click(stopButton!)
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
