// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { RunStatusIndicator } from "./run-status"
import { buildRunCardModel } from "./sidebar/historyRowModel"
import { resolveRunHeaderStatus, resolveRunStatus, STATUS_TEXT } from "@/lib/constants"
import { isTerminalHistoricalStatus } from "@/lib/runSelection"

describe("needs_revision status", () => {
  it("renders a Needs revision badge with warning styling", () => {
    render(<RunStatusIndicator status={resolveRunStatus("needs_revision")} />)
    const label = screen.getByText("Needs revision")
    expect(label).toHaveClass(STATUS_TEXT.needs_revision)
    expect(label).toHaveClass("text-intent-warning")
  })

  it("is terminal and shows a full progress bar on sidebar cards", () => {
    expect(isTerminalHistoricalStatus("needs_revision")).toBe(true)
    const model = buildRunCardModel({
      source: "in-progress",
      entry: {
        workflow_id: "wf-9",
        topic: "Topic",
        status: "needs_revision",
        db_path: "/tmp/db",
        created_at: "2026-01-01T00:00:00Z",
      },
      liveRun: null,
      selectedWorkflowId: null,
      openingId: null,
      resumingId: null,
      options: {},
    })
    expect(model.statusKey).toBe("needs_revision")
    expect(model.progressValue).toBe(1)
    expect(model.rowIsRunning).toBe(false)
  })

  it("resolves the run header label", () => {
    expect(
      resolveRunHeaderStatus({
        status: "done",
        isDone: true,
        isRunning: false,
        isCancelled: false,
        isFailed: false,
        isAwaitingReview: false,
        isNeedsRevision: true,
      }).label,
    ).toBe("Needs revision")
  })
})
