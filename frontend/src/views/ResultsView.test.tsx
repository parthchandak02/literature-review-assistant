// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ResultsView } from "./ResultsView"

describe("ResultsView locked state", () => {
  it("navigates to Activity from the locked state", async () => {
    const user = userEvent.setup()
    const onOpenActivity = vi.fn()
    render(
      <ResultsView
        outputs={{}}
        isDone={false}
        runId="run-1"
        workflowId="wf-1"
        onOpenActivity={onOpenActivity}
      />,
    )
    await user.click(screen.getByRole("button", { name: /Go to Activity/ }))
    expect(onOpenActivity).toHaveBeenCalledTimes(1)
  })
})
