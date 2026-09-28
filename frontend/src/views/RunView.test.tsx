// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { RunView } from "./RunView"
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"

vi.mock("@/views/ActivityView", () => ({ ActivityView: () => <div>activity-view</div> }))
vi.mock("@/hooks/useScreeningReview", () => ({ useScreeningPendingCount: () => null }))
vi.mock("@/hooks/useHistoricalEvents", () => ({
  useHistoricalEvents: () => ({ data: [], isPending: false }),
}))

const emptyCost = { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] }

function renderRunView(historicalStatus: string, activeTab: RunTab = "activity") {
  const run: SelectedRun = {
    runId: `run-${historicalStatus}`,
    workflowId: `wf-${historicalStatus}`,
    topic: "Topic",
    dbPath: null,
    isDone: false,
    startedAt: null,
    historicalStatus,
  }
  const onTabChange = vi.fn()
  render(
    <RunView
      run={run}
      events={[]}
      isViewingLiveRun={false}
      status={historicalStatus}
      costStats={emptyCost}
      activeTab={activeTab}
      onTabChange={onTabChange}
      historyOutputs={{}}
      liveOutputs={{}}
      dbUnlocked={false}
      isLive={false}
    />,
  )
  return onTabChange
}

describe("RunView auto-routing", () => {
  it("routes awaiting_review runs opened on Activity to the review tab and shows the banner", () => {
    const onTabChange = renderRunView("awaiting_review")
    expect(onTabChange).toHaveBeenCalledWith("review-screening")
    expect(screen.getByRole("status")).toHaveTextContent("screening decisions need your approval")
  })

  it("routes config_ready and awaiting_prospero runs to Config", () => {
    expect(renderRunView("config_ready")).toHaveBeenCalledWith("config")
    expect(renderRunView("awaiting_prospero")).toHaveBeenCalledWith("config")
  })

  it("leaves non-default tabs and non-gate runs alone", () => {
    expect(renderRunView("awaiting_review", "cost")).not.toHaveBeenCalled()
    expect(renderRunView("completed")).not.toHaveBeenCalled()
  })
})
