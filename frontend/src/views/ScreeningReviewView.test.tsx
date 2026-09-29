// @vitest-environment jsdom
import "@/test/dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ScreeningReviewView } from "./ScreeningReviewView"
import { ScreeningResumeError } from "@/hooks/runSession/useRunGateActions"
import { screeningOverridesStorageKey } from "@/hooks/useScreeningReview"
import type { ScreenedPaper, ScreeningSummary } from "@/lib/api"

function paper(p: Partial<ScreenedPaper> & { paper_id: string; title: string }): ScreenedPaper {
  return {
    authors: "Doe",
    year: 2024,
    source_database: "pubmed",
    doi: null,
    abstract: null,
    stage: "title_abstract",
    decision: "include",
    reason: null,
    confidence: 0.5,
    ...p,
  }
}

const summary: ScreeningSummary = {
  run_id: "run-1",
  total: 3,
  instructions: "",
  papers: [
    paper({
      paper_id: "p1",
      title: "Paper One",
      decision: "uncertain",
      confidence: 0.4,
      abstract: "A long abstract. ".repeat(40),
      reason: "Population unclear",
    }),
    paper({ paper_id: "p2", title: "Paper Two", decision: "include", confidence: 0.9 }),
    paper({
      paper_id: "p3",
      title: "Paper Three",
      decision: "exclude",
      final_decision: "exclude",
      confidence: 0.95,
      decided_by: "adjudicator",
      exclusion_reason: "wrong_population",
    }),
  ],
  thresholds: { include: 0.85, exclude: 0.8, source: "calibration" },
}

const fetchScreeningSummary = vi.fn(async () => summary)

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, fetchScreeningSummary: () => fetchScreeningSummary() }
})

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

function renderView(onApprove?: (o: unknown[]) => Promise<void>, readOnly = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ScreeningReviewView runId="run-1" workflowId="wf-1" onApproveAndResume={onApprove} readOnly={readOnly} />
    </QueryClientProvider>,
  )
}

async function rowFor(title: string) {
  return (await screen.findByRole("row", { name: title })) as HTMLElement
}

describe("ScreeningReviewView", () => {
  beforeEach(() => {
    fetchScreeningSummary.mockClear()
  })

  it("is read-only once screening was approved", async () => {
    sessionStorage.setItem(
      screeningOverridesStorageKey("wf-1"),
      JSON.stringify([{ paper_id: "p2", decision: "exclude" }]),
    )
    const user = userEvent.setup()
    renderView(vi.fn(async () => {}), true)
    const row = await rowFor("Paper Two")
    expect(screen.getByTestId("screening-read-only-banner")).toHaveTextContent(
      "Screening was approved; this is a read-only view of the final decisions",
    )
    expect(screen.queryByRole("progressbar")).toBeNull()
    expect(screen.queryByText(/Reviewed \d+ of/)).toBeNull()
    expect(screen.queryByTestId("screening-approval-bar")).toBeNull()
    expect(screen.queryByRole("button", { name: /Approve screening/ })).toBeNull()
    expect(within(row).queryByRole("button", { name: "Include" })).toBeNull()
    expect(within(row).queryByRole("checkbox")).toBeNull()
    expect(within(row).queryByText(/Override:/)).toBeNull()
    expect(screen.queryByLabelText("Select all matching")).toBeNull()
    expect(screen.queryByRole("button", { name: /Undo/ })).toBeNull()
    expect(screen.queryByRole("button", { name: /^Overridden/ })).toBeNull()

    row.focus()
    await user.keyboard("e")
    expect(within(row).queryByText(/Override:/)).toBeNull()
    await user.keyboard("{Enter}")
    expect(within(row).getByRole("button", { name: /Paper Two/ })).toHaveAttribute("aria-expanded", "true")
    expect(sessionStorage.getItem(screeningOverridesStorageKey("wf-1"))).toContain("p2")
  })

  it("loads saved overrides once the gate turns editable", async () => {
    sessionStorage.setItem(
      screeningOverridesStorageKey("wf-1"),
      JSON.stringify([{ paper_id: "p2", decision: "exclude" }]),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const view = (readOnly: boolean) => (
      <QueryClientProvider client={client}>
        <ScreeningReviewView runId="run-1" workflowId="wf-1" readOnly={readOnly} />
      </QueryClientProvider>
    )
    const { rerender } = render(view(true))
    await rowFor("Paper Two")
    rerender(view(false))
    expect(within(await rowFor("Paper Two")).getByText("Override: Exclude")).toBeInTheDocument()
    expect(sessionStorage.getItem(screeningOverridesStorageKey("wf-1"))).toContain("p2")
  })

  it("shows live counts and sorts lowest confidence first", async () => {
    renderView()
    expect(await screen.findByTestId("screening-reviewer-line")).toHaveTextContent(
      "3 screened by reviewers · 1 include · 1 exclude · 1 uncertain · 0 overridden",
    )
    expect(screen.queryByTestId("screening-automation-line")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Removed by automation/ })).not.toBeInTheDocument()
    expect(screen.getByText("Reviewed 0 of 3")).toBeInTheDocument()
    expect(screen.getByText(/Calibrated on this run: .* 85% confident to include/)).toBeInTheDocument()
    const rows = screen.getAllByRole("row")
    expect(rows.map((r) => r.getAttribute("aria-label"))).toEqual(["Paper One", "Paper Two", "Paper Three"])
  })

  it("keeps automation removals out of reviewer counts and lets them be rescued", async () => {
    const automated = (paper_id: string, title: string, automation_step: string) =>
      paper({
        paper_id,
        title,
        decision: "exclude",
        final_decision: "exclude",
        confidence: null,
        decided_by: "keyword_filter",
        automation_step,
      })
    fetchScreeningSummary.mockResolvedValueOnce({
      ...summary,
      total: 6,
      papers: [
        ...summary.papers,
        automated("a1", "Auto One", "keyword_ranking"),
        automated("a2", "Auto Two", "keyword_ranking"),
        automated("a3", "Auto Three", "metadata_filter"),
        paper({ paper_id: "f1", title: "Full Text Out", decision: "exclude", stage: "fulltext", confidence: 0.9 }),
      ],
    })
    const user = userEvent.setup()
    const onApprove = vi.fn(async () => {})
    renderView(onApprove)
    await rowFor("Paper One")
    expect(screen.getByTestId("screening-reviewer-line")).toHaveTextContent(
      "4 screened by reviewers · 1 include · 2 exclude (1 title/abstract, 1 full text) · 1 uncertain · 0 overridden",
    )
    expect(screen.getByTestId("screening-automation-line")).toHaveTextContent("Removed by automation 3")
    expect(screen.getByText("Reviewed 0 of 4")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^All\s*4$/ })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /^Exclude\s*2$/ })).toBeInTheDocument()
    expect(screen.getAllByRole("row")).toHaveLength(4)

    await user.click(screen.getByRole("button", { name: /^Removed by automation\s*3$/ }))
    expect(screen.getAllByRole("row").map((r) => r.getAttribute("aria-label"))).toEqual([
      "Auto One",
      "Auto Three",
      "Auto Two",
    ])
    const row = await rowFor("Auto Three")
    expect(within(row).getByText(/Auto-removed · metadata filter/)).toBeInTheDocument()
    await user.click(within(row).getByRole("button", { name: "Include" }))
    expect(screen.getByTestId("screening-automation-line")).toHaveTextContent("Removed by automation 3 (1 rescued)")
    expect(screen.getByText("Reviewed 0 of 4")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Approve screening/ }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent("2 included")
    expect(dialog).toHaveTextContent("2 excluded")
    expect(dialog).toHaveTextContent("2 removed by automation")
    await user.click(within(dialog).getByRole("button", { name: "Approve and start extraction" }))
    expect(onApprove).toHaveBeenCalledWith([{ paper_id: "a3", decision: "include" }])
  })

  it("shows who decided and why a paper was excluded, and lets it be rescued", async () => {
    const user = userEvent.setup()
    renderView()
    await rowFor("Paper One")
    await user.click(screen.getByRole("button", { name: /^Exclude\s*1$/ }))
    expect(screen.getAllByRole("row").map((r) => r.getAttribute("aria-label"))).toEqual(["Paper Three"])
    const row = await rowFor("Paper Three")
    await user.click(within(row).getByRole("button", { name: /Paper Three/ }))
    expect(within(row).getByText("AI adjudicator")).toBeInTheDocument()
    expect(within(row).getByText("Wrong population")).toBeInTheDocument()
    await user.click(within(row).getByRole("button", { name: "Include" }))
    expect(within(row).getByText("Override: Include")).toBeInTheDocument()
  })

  it("only overrides with the opposite action and persists overrides across remounts", async () => {
    const user = userEvent.setup()
    const first = renderView()
    const row = await rowFor("Paper Two")
    const include = within(row).getByRole("button", { name: "Include" })
    expect(include).toHaveAttribute("aria-pressed", "true")
    await user.click(include)
    expect(within(row).queryByText(/Override:/)).not.toBeInTheDocument()

    await user.click(within(row).getByRole("button", { name: "Exclude" }))
    expect(within(row).getByText("Override: Exclude")).toBeInTheDocument()
    first.unmount()

    renderView()
    const again = await rowFor("Paper Two")
    expect(within(again).getByText("Override: Exclude")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Approve screening \(1 override\)/ })).toBeInTheDocument()
  })

  it("seeds the reason input from the persisted override", async () => {
    sessionStorage.setItem(
      screeningOverridesStorageKey("wf-1"),
      JSON.stringify([{ paper_id: "p1", decision: "include", reason: "Meets PICO" }]),
    )
    const user = userEvent.setup()
    renderView()
    const row = await rowFor("Paper One")
    const toggle = within(row).getByRole("button", { name: /Paper One/ })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    const input = within(row).getByLabelText("Reason for override")
    expect(input).toHaveValue("Meets PICO")
    await user.type(input, " too")
    expect(input).toHaveValue("Meets PICO too")
    expect(within(row).getByText("Population unclear")).toBeInTheDocument()
    expect(within(row).getByText("Title and abstract")).toBeInTheDocument()
  })

  it("drives triage from the keyboard with undo", async () => {
    const user = userEvent.setup()
    renderView()
    const one = await rowFor("Paper One")
    const two = await rowFor("Paper Two")
    one.focus()
    await user.keyboard("j")
    expect(two).toHaveFocus()
    await user.keyboard("e")
    expect(within(two).getByText("Override: Exclude")).toBeInTheDocument()
    await user.keyboard("k")
    expect(one).toHaveFocus()
    await user.keyboard("i")
    expect(within(one).getByText("Override: Include")).toBeInTheDocument()
    await user.keyboard("x")
    expect(one).toHaveAttribute("aria-selected", "true")
    await user.keyboard("{Enter}")
    expect(within(one).getByRole("button", { name: /Paper One/ })).toHaveAttribute("aria-expanded", "true")

    await user.keyboard("u")
    expect(within(one).queryByText("Override: Include")).not.toBeInTheDocument()
    await user.keyboard("u")
    expect(within(two).queryByText("Override: Exclude")).not.toBeInTheDocument()

    const input = screen.getByLabelText("Search titles and authors")
    await user.type(input, "ej")
    expect(within(one).queryByText(/Override:/)).not.toBeInTheDocument()
  })

  it("applies bulk actions to the selection", async () => {
    const user = userEvent.setup()
    renderView()
    await rowFor("Paper One")
    await user.click(screen.getByLabelText("Select all matching"))
    await user.click(screen.getByRole("button", { name: "Exclude selected" }))
    expect(screen.getAllByText("Override: Exclude")).toHaveLength(2)
    await user.click(screen.getByRole("button", { name: "Clear overrides" }))
    expect(screen.queryByText(/Override:/)).not.toBeInTheDocument()
  })

  it("confirms with a summary before approving", async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn(async () => {})
    renderView(onApprove)
    await rowFor("Paper One")
    await user.click(screen.getByRole("button", { name: "Approve screening" }))
    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveTextContent(
      "1 included, 1 uncertain → kept in and sent to extraction with the included papers, 1 excluded, no overrides. Extraction will start and incur model cost.",
    )
    expect(onApprove).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole("button", { name: "Approve and start extraction" }))
    expect(onApprove).toHaveBeenCalledWith([])
    expect(await screen.findByText(/Screening approved. Extraction is starting./)).toBeInTheDocument()
  })

  it("keeps overrides and offers retry when approval fails", async () => {
    const user = userEvent.setup()
    const onApprove = vi.fn(async () => {
      throw new Error("Server exploded")
    })
    renderView(onApprove)
    const row = await rowFor("Paper Two")
    await user.click(within(row).getByRole("button", { name: "Exclude" }))
    await user.click(screen.getByRole("button", { name: /Approve screening/ }))
    await user.click(await screen.findByRole("button", { name: "Approve and start extraction" }))

    expect(onApprove).toHaveBeenCalledWith([expect.objectContaining({ paper_id: "p2", decision: "exclude" })])
    expect(await screen.findByRole("alert")).toHaveTextContent("Approval failed: Server exploded")
    expect(within(row).getByText("Override: Exclude")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry approval" })).toBeEnabled()
  })

  it("separates a resume failure and retries resume only", async () => {
    const user = userEvent.setup()
    const onApprove = vi
      .fn<(o: unknown[]) => Promise<void>>()
      .mockRejectedValueOnce(new ScreeningResumeError("resume broke"))
      .mockResolvedValueOnce(undefined)
    renderView(onApprove)
    await rowFor("Paper One")
    await user.click(screen.getByRole("button", { name: "Approve screening" }))
    await user.click(await screen.findByRole("button", { name: "Approve and start extraction" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Screening approved, but the run didn't resume: resume broke",
    )
    expect(screen.queryByRole("button", { name: /Approve screening/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Retry resume" }))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(onApprove).toHaveBeenCalledTimes(2)
    expect(await screen.findByText(/Extraction is starting/)).toBeInTheDocument()
  })
})
