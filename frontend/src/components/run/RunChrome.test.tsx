// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Activity, FileText } from "lucide-react"
import { RunChrome } from "./RunChrome"
import { computeRunChrome } from "@/hooks/useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"

const run: SelectedRun = {
  runId: "run-1",
  workflowId: "wf-1",
  topic: "Topic",
  dbPath: null,
  isDone: true,
  startedAt: null,
  historicalStatus: "needs_revision",
}

describe("RunChrome needs_revision", () => {
  it("shows the Needs revision status, links to results, and offers the package download", async () => {
    const user = userEvent.setup()
    const onTabChange = vi.fn()
    const chrome = computeRunChrome({
      run,
      events: [],
      effectiveEvents: [],
      isViewingLiveRun: false,
      status: "done",
      costStats: { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] },
    })
    expect(chrome.isNeedsRevision).toBe(true)

    render(
      <RunChrome
        run={run}
        chrome={chrome}
        tabItems={[
          { id: "activity", label: "Activity", icon: Activity },
          { id: "results", label: "Results", icon: FileText },
        ]}
        activeTab="activity"
        onTabChange={onTabChange}
        isViewingLiveRun={false}
        status="done"
      />,
    )

    const status = screen.getByText("Needs revision")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(screen.getByRole("button", { name: /Download submission package/ })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Review audit findings/ }))
    expect(onTabChange).toHaveBeenCalledWith("results")
  })
})
