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
import type { RunTab, SelectedRun } from "@/context/runSessionTypes"
import type { FunnelStage } from "@/lib/funnelStages"

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

function renderChrome(
  selected: SelectedRun,
  onTabChange = vi.fn(),
  activeTab: RunTab = "activity",
  chromeOverrides: Partial<RunChromeVM> = {},
) {
  render(
    <RunChrome
      run={selected}
      chrome={{ ...chromeFor(selected), ...chromeOverrides }}
      tabItems={tabItems}
      activeTab={activeTab}
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

  it("keeps a highlighted Screening tab when a finished run's screening page is open", () => {
    renderChrome(completed, vi.fn(), "review-screening")
    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab")
    expect(tabs.map((t) => t.textContent)).toEqual(["Activity", "Screening", "Results", "Cost"])
    expect(screen.getByRole("tab", { name: /Screening/ })).toHaveAttribute("aria-selected", "true")
  })

  it("hides the screening tab on a finished run elsewhere", () => {
    renderChrome(completed)
    expect(screen.queryByRole("tab", { name: /Screening/ })).toBeNull()
  })

  it("keeps labels sans and puts outcome numbers, cost, and workflow id in .num", () => {
    renderChrome(completed)
    const strip = screen.getByTestId("run-meta-strip").parentElement!
    expect(strip.className).toMatch(/font-sans/)
    expect(strip.className).not.toMatch(/text-meta|font-mono/)
    const nums = Array.from(screen.getByTestId("run-meta-strip").querySelectorAll(".num")).map((el) => el.textContent)
    expect(nums).toEqual(["6", "1,716", "$1.23", "wf-1"])
    expect(screen.getByRole("button", { name: "$1.23" }).className).not.toMatch(/intent-/)
  })

  const stages: FunnelStage[] = [
    { key: "identified", label: "identified", count: 1716, colorClass: "text-intent-info", kind: "count" },
    { key: "duplicates", label: "duplicates removed", count: 168, colorClass: "text-muted", kind: "removed" },
    { key: "screened", label: "screened", count: 209, colorClass: "text-intent-primary", kind: "count" },
    { key: "sought", label: "sought for retrieval", count: 60, colorClass: "text-intent-active", kind: "count" },
    { key: "assessed", label: "assessed for eligibility", count: 57, colorClass: "text-intent-warning", kind: "count" },
    { key: "included", label: "included", count: 6, colorClass: "text-intent-success", kind: "count" },
  ]

  it("shows a toned compact funnel chain that opens the full funnel", async () => {
    const user = userEvent.setup()
    renderChrome(completed, vi.fn(), "activity", { displayFunnelStages: stages })
    const chain = screen.getByTestId("run-funnel-chain")
    const counts = Array.from(chain.querySelectorAll(".num")).map((el) => [el.textContent, el.className])
    expect(counts.map(([text]) => text)).toEqual(["1,716", "209", "57", "6"])
    expect(counts[0][1]).toMatch(/text-intent-info/)
    expect(counts[3][1]).toMatch(/text-intent-success/)
    expect(screen.queryByRole("button", { name: /^Funnel$/ })).toBeNull()

    await user.click(screen.getByRole("button", { name: "Show full funnel" }))
    const removed = await screen.findByText("−168")
    expect(removed.className).toMatch(/num/)
    expect(removed.closest("li")!.className).toMatch(/text-muted/)
    const sought = screen.getByText("60")
    expect(sought.className).toMatch(/text-intent-active/)
    expect(sought.className).toMatch(/text-right/)
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
