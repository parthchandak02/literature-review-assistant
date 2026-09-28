// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Activity, BarChart3, FileText } from "lucide-react"
import { toast } from "sonner"
import { RunChrome } from "./RunChrome"
import { formatChromeCost, formatOutcome } from "./runChromeFormat"
import { computeRunChrome, type RunChromeVM } from "@/hooks/useRunChrome"
import type { SelectedRun } from "@/context/runSessionTypes"

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const run: SelectedRun = {
  runId: "run-1",
  workflowId: "wf-1",
  topic: "Topic",
  dbPath: null,
  isDone: true,
  startedAt: null,
  historicalStatus: "needs_revision",
}

const emptyCost = { total_cost: 0, total_tokens_in: 0, total_tokens_out: 0, total_calls: 0, by_model: [], by_phase: [] }

const tabItems = [
  { id: "activity" as const, label: "Activity", icon: Activity },
  { id: "results" as const, label: "Results", icon: FileText },
  { id: "cost" as const, label: "Cost", icon: BarChart3 },
]

function chromeFor(selected: SelectedRun): RunChromeVM {
  return computeRunChrome({
    run: selected,
    events: [],
    effectiveEvents: [],
    isViewingLiveRun: false,
    status: "done",
    costStats: emptyCost,
  })
}

function renderChrome(selected: SelectedRun, onTabChange = vi.fn()) {
  render(
    <RunChrome
      run={selected}
      chrome={chromeFor(selected)}
      tabItems={tabItems}
      activeTab="activity"
      onTabChange={onTabChange}
      isViewingLiveRun={false}
      status="done"
    />,
  )
  return onTabChange
}

describe("RunChrome needs_revision", () => {
  it("shows the Needs revision status, links to results, and offers the package download", async () => {
    const user = userEvent.setup()
    expect(chromeFor(run).isNeedsRevision).toBe(true)
    const onTabChange = renderChrome(run)

    const status = screen.getByText("Needs revision")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(await screen.findByRole("button", { name: /Download submission package/ })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Review audit findings/ }))
    expect(onTabChange).toHaveBeenCalledWith("results")
  })
})

describe("RunChrome info strip", () => {
  const completed: SelectedRun = {
    ...run,
    historicalStatus: "completed",
    papersFound: 1716,
    papersIncluded: 6,
    historicalCost: 1.2345,
  }

  it("leads with the outcome and a neutral 2dp cost", async () => {
    const onTabChange = renderChrome(completed)
    expect(screen.getByTestId("run-outcome")).toHaveTextContent("6 included of 1,716 records")
    const cost = screen.getByRole("button", { name: "$1.23" })
    expect(cost.className).not.toMatch(/intent-warning/)
    await userEvent.setup().click(cost)
    expect(onTabChange).toHaveBeenCalledWith("cost")
    expect(screen.queryByText("|")).toBeNull()
  })

  it("announces a successful copy and toasts on failure", async () => {
    const user = userEvent.setup()
    renderChrome(completed)
    const copy = screen.getByRole("button", { name: "Copy workflow ID" })

    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValueOnce(undefined)
    await user.click(copy)
    expect(writeText).toHaveBeenCalledWith("wf-1")
    expect(await screen.findByText("Copied")).toHaveAttribute("aria-live", "polite")

    writeText.mockRejectedValueOnce(new Error("denied"))
    await user.click(copy)
    expect(toast.error).toHaveBeenCalled()
  })

  it("puts the review tab second when awaiting review", () => {
    renderChrome({ ...run, historicalStatus: "awaiting_review", isDone: false })
    const names = within(screen.getByRole("tablist"))
      .getAllByRole("tab")
      .map((t) => t.textContent)
    expect(names).toEqual(["Activity", "Review Screening", "Results", "Cost"])
  })
})

describe("runChromeFormat", () => {
  it("formats cost and outcome", () => {
    expect(formatChromeCost(0.004)).toBe("<$0.01")
    expect(formatChromeCost(12.345)).toBe("$12.35")
    expect(formatOutcome(6, 1716)).toBe("6 included of 1,716 records")
    expect(formatOutcome(null, 1716)).toBe("1,716 records")
    expect(formatOutcome(null, null)).toBeNull()
  })
})
