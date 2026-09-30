// @vitest-environment jsdom
import "@/test/dom"
import type { ReactElement } from "react"
import { describe, expect, it, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { TooltipProvider } from "@/components/ui/tooltip"
import type { HistoryEntry } from "@/lib/api"
import { RunNavCard, type RunNavCardProps } from "./RunNavCard"
import { dismissOpenCardMenus } from "./runCardMenuGuard"
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

  it("shows found, included, cost and workflow id without a toggle", () => {
    renderHistoryCard({ papers_found: 1716, papers_included: 6, total_cost: 1.205 })
    expect(screen.getByText("1,716 found, 6 included")).toBeInTheDocument()
    expect(screen.getByText("$1.21")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Copy workflow ID wf-0002" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /details|funnel/i })).not.toBeInTheDocument()
  })

  it("keeps the workflow id on drafts with no search results", () => {
    renderHistoryCard({ status: "config_ready" })
    expect(screen.getByRole("button", { name: "Copy workflow ID wf-0002" })).toBeInTheDocument()
    expect(screen.queryByText(/→/)).not.toBeInTheDocument()
  })

  it("reveals the full funnel only when it has extra stages", async () => {
    const user = userEvent.setup()
    const model = buildRunCardModel({
      source: "live",
      liveRun: {
        runId: "run-1",
        topic: "Topic",
        status: "streaming",
        cost: 0.4,
        workflowId: "wf-1",
        funnelStages: [
          { key: "found", label: "found", count: 1716, colorClass: "text-intent-info" },
          { key: "screened", label: "screened", count: 300, colorClass: "text-foreground" },
          { key: "included", label: "included", count: 6, colorClass: "text-intent-success" },
        ],
      },
      isSelected: false,
      isRunning: true,
    })
    renderWithProvider(
      <RunNavCard model={model} collapsed={false} wfIdCopied={null} onCopyWorkflowId={async () => {}} />,
    )
    const toggle = screen.getByRole("button", { name: "Show full funnel" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
    expect(screen.queryByText("screened")).not.toBeInTheDocument()
    await user.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("screened")).toBeInTheDocument()
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

  it("an outside press only dismisses the menu, it does not open the card beneath", async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    const onSelectEntry = vi.fn()
    const laneCard = (workflowId: string, topic: string) => (
      <RunNavCard
        model={buildRunCardModel({
          source: "lane",
          entry: { ...baseEntry, workflow_id: workflowId, topic, status: "completed" },
          variant: "completed",
          isSelected: false,
        })}
        collapsed={false}
        wfIdCopied={null}
        onCopyWorkflowId={async () => {}}
        onSelectEntry={onSelectEntry}
        onArchive={vi.fn()}
      />
    )
    renderWithProvider(
      <>
        {laneCard("wf-0010", "First review")}
        {laneCard("wf-0011", "Second review")}
      </>,
    )
    const [firstMenu] = screen.getAllByRole("button", { name: "More actions" })
    await user.click(firstMenu)
    expect(screen.getByRole("menu")).toBeInTheDocument()

    await user.click(screen.getByText("Second review"))
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(onSelectEntry).not.toHaveBeenCalled()

    const now = performance.now()
    const clock = vi.spyOn(performance, "now").mockReturnValue(now + 1000)
    try {
      await user.click(screen.getByText("Second review"))
      expect(onSelectEntry).toHaveBeenCalledWith(expect.objectContaining({ workflow_id: "wf-0011" }))
    } finally {
      clock.mockRestore()
    }
  })

  it("closes when a touch just outside the menu is snapped onto the menu panel", async () => {
    const user = userEvent.setup()
    renderHistoryCard({}, { onArchive: vi.fn() })
    await user.click(screen.getByRole("button", { name: "More actions" }))
    const menu = screen.getByRole("menu")
    vi.spyOn(menu, "getBoundingClientRect").mockReturnValue(new DOMRect(50, 700, 220, 100))

    fireEvent.pointerDown(menu, { clientX: 60, clientY: 702 })
    expect(screen.getByRole("menu")).toBeInTheDocument()

    fireEvent.pointerDown(menu, { clientX: 200, clientY: 697 })
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
  })

  it("lets the drawer close an open card menu without closing itself", async () => {
    const user = userEvent.setup()
    renderHistoryCard({}, { onArchive: vi.fn() })
    expect(dismissOpenCardMenus()).toBe(false)
    await user.click(screen.getByRole("button", { name: "More actions" }))
    expect(screen.getByRole("menu")).toBeInTheDocument()
    let dismissed = false
    act(() => {
      dismissed = dismissOpenCardMenus()
    })
    expect(dismissed).toBe(true)
    expect(screen.queryByRole("menu")).not.toBeInTheDocument()
    expect(dismissOpenCardMenus()).toBe(false)
  })

  it("Add note reveals and focuses the note field", async () => {
    const user = userEvent.setup()
    renderHistoryCard({}, { onNoteChange: vi.fn(), onArchive: vi.fn() })
    expect(screen.queryByPlaceholderText("Add a note...")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "More actions" }))
    await user.click(screen.getByRole("menuitem", { name: "Add note" }))
    expect(await screen.findByPlaceholderText("Add a note...")).toBeInTheDocument()
  })

  it("shows the created time in the status row for runs started today", () => {
    renderHistoryCard({ workflow_id: "wf-0004", created_at: new Date().toISOString() })
    expect(screen.getByText("wf-0004")).toBeInTheDocument()
    expect(screen.getByText(/^\d{1,2}:\d{2}/)).toBeInTheDocument()
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
