// @vitest-environment jsdom
import "@/test/dom"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { HistoryEntry } from "@/lib/api"
import { RunNavCard, type RunNavCardProps } from "./RunNavCard"
import { buildRunCardModel } from "./historyRowModel"

function renderWithProvider(ui: ReactElement) {
  return render(<TooltipProvider>{ui}</TooltipProvider>)
}

const baseEntry: HistoryEntry = {
  workflow_id: "wf-0002",
  topic: "What hospital-based models of geriatric care improve outcomes?",
  status: "failed",
  db_path: "/tmp/runtime.db",
  created_at: "2026-09-02T07:00:00Z",
  papers_found: 0,
  papers_included: 0,
}

function renderLiveCard(onCancel: () => Promise<void>) {
  const model = buildRunCardModel({
    source: "live",
    liveRun: { runId: "run-1", topic: "Topic", status: "streaming", cost: 0, workflowId: "wf-1" },
    isSelected: true,
    isRunning: true,
  })
  return renderWithProvider(
    <RunNavCard
      model={model}
      collapsed={false}
      wfIdCopied={null}
      onCopyWorkflowId={async () => {}}
      onCancel={onCancel}
    />,
  )
}

function renderHistoryCard(
  entry: Partial<HistoryEntry>,
  props: Partial<RunNavCardProps> = {},
) {
  const model = buildRunCardModel({
    source: "in-progress",
    entry: { ...baseEntry, ...entry },
    liveRun: null,
    selectedWorkflowId: null,
    openingId: null,
    resumingId: null,
    options: { onHideCompleted: async () => {}, onArchive: async () => {} },
  })
  return renderWithProvider(
    <RunNavCard
      model={model}
      collapsed={false}
      wfIdCopied={null}
      onCopyWorkflowId={async () => {}}
      {...props}
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

describe("RunNavCard structure", () => {
  it("has no interactive element nested inside another", () => {
    const { container } = renderHistoryCard(
      { papers_found: 120, papers_included: 6, total_cost: 1.2 },
      { onArchive: vi.fn(), onMoveToCompleted: vi.fn(), onNoteChange: vi.fn() },
    )
    expect(container.querySelectorAll("button button, button [role=button], button textarea")).toHaveLength(0)
  })

  it("Space on the actions trigger does not select the card", async () => {
    const user = userEvent.setup()
    const onSelectEntry = vi.fn()
    renderHistoryCard({}, { onSelectEntry, onArchive: vi.fn() })
    screen.getByRole("button", { name: "More actions" }).focus()
    await user.keyboard(" ")
    expect(onSelectEntry).not.toHaveBeenCalled()
    expect(await screen.findByRole("menuitem", { name: "Archive" })).toBeInTheDocument()
  })

  it("hides funnel numbers until search has found records", () => {
    renderHistoryCard({ papers_found: 0, papers_included: 0 })
    expect(screen.queryByText(/found|included/)).not.toBeInTheDocument()
  })

  it("shows one key metric once search has run", () => {
    renderHistoryCard({ papers_found: 1716, papers_included: 6 })
    expect(screen.getByText("6 included")).toBeInTheDocument()
  })

  it("explains why a card cannot be opened", () => {
    renderHistoryCard({ db_path: "" })
    expect(screen.getByText("No database yet")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /hospital-based/ })).toHaveAttribute("aria-disabled", "true")
  })
})

describe("RunNavCard actions menu", () => {
  it("names lane destinations for archived reviews", async () => {
    const user = userEvent.setup()
    const onMoveToInProgress = vi.fn()
    const onDelete = vi.fn()
    const model = buildRunCardModel({
      source: "lane",
      entry: { ...baseEntry, is_archived: true },
      variant: "archived",
      isSelected: false,
    })
    renderWithProvider(
      <RunNavCard
        model={model}
        collapsed={false}
        wfIdCopied={null}
        onCopyWorkflowId={async () => {}}
        onArchive={vi.fn()}
        onMoveToCompleted={vi.fn()}
        onMoveToInProgress={onMoveToInProgress}
        onDelete={onDelete}
      />,
    )
    await user.click(screen.getByRole("button", { name: "More actions" }))
    expect(screen.getByRole("menuitem", { name: "Move to Completed" })).toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: "Archive" })).not.toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: /^Restore/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole("menuitem", { name: "Move to In progress" }))
    expect(onMoveToInProgress).toHaveBeenCalledWith("wf-0002")
  })

  it("Add note reveals and focuses the note field", async () => {
    const user = userEvent.setup()
    renderHistoryCard({}, { onNoteChange: vi.fn(), onArchive: vi.fn() })
    expect(screen.queryByPlaceholderText("Add a note...")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "More actions" }))
    await user.click(screen.getByRole("menuitem", { name: "Add note" }))
    expect(await screen.findByPlaceholderText("Add a note...")).toBeInTheDocument()
  })

  it("shows a muted workflow id and created time line", () => {
    renderHistoryCard({ workflow_id: "wf-0004" })
    expect(screen.getByText(/^wf-0004 · .+\d{1,2}:\d{2}/)).toBeInTheDocument()
  })

  it("shows a read-only note on lane cards", () => {
    const model = buildRunCardModel({
      source: "lane",
      entry: { ...baseEntry, notes: "Pilot for the India grant" },
      variant: "completed",
      isSelected: false,
    })
    renderWithProvider(
      <RunNavCard model={model} collapsed={false} wfIdCopied={null} onCopyWorkflowId={async () => {}} />,
    )
    expect(screen.getByText("Pilot for the India grant")).toBeInTheDocument()
  })

  it("uses the shared status label instead of hard-coded caps", () => {
    renderHistoryCard({ status: "streaming", live_run_id: null })
    expect(screen.getByText("Reconnecting")).toBeInTheDocument()
  })
})
