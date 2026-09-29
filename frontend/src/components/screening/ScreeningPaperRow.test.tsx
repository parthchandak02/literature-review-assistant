// @vitest-environment jsdom
import "@/test/dom"
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import type { ScreenedPaper, ScreeningOverride } from "@/lib/api"
import { ScreeningPaperRow } from "./ScreeningPaperRow"
import type { ScreeningRowData } from "./screeningModel"

function makeRow(overrides: Partial<ScreenedPaper> = {}): ScreeningRowData {
  const paper: ScreenedPaper = {
    paper_id: "p1",
    title: "Pickleball and balance",
    authors: "",
    year: 2024,
    source_database: "pubmed",
    doi: null,
    abstract: null,
    stage: "title_abstract",
    decision: "exclude",
    reason: null,
    confidence: 0.9,
    ...overrides,
  }
  return {
    key: "p1",
    paper,
    title: paper.title ?? "",
    authors: "",
    abstract: "",
    reason: "",
    automationStep: paper.automation_step ?? null,
  }
}

function renderRow(row: ScreeningRowData, override: ScreeningOverride | null = null) {
  const noop = vi.fn()
  render(
    <div role="grid">
      <ScreeningPaperRow
        row={row}
        override={override}
        focused
        expanded={false}
        selected={false}
        onDecide={noop}
        onClearOverride={noop}
        onReasonChange={noop}
        onToggleExpanded={noop}
        onToggleSelected={noop}
        onFocusRow={noop}
      />
    </div>,
  )
  return {
    include: screen.getByRole("button", { name: "Include" }),
    exclude: screen.getByRole("button", { name: "Exclude" }),
  }
}

describe("ScreeningPaperRow decision buttons", () => {
  it("marks the AI default as pressed without the solid human fill", () => {
    const { include, exclude } = renderRow(makeRow())
    expect(exclude).toHaveAttribute("aria-pressed", "true")
    expect(exclude).toHaveAttribute("data-decision-source", "ai")
    expect(exclude.className).not.toMatch(/bg-intent-danger-solid/)
    expect(exclude.className).toMatch(/bg-intent-danger-subtle/)
    expect(include).toHaveAttribute("aria-pressed", "false")
    expect(include).not.toHaveAttribute("data-decision-source")
  })

  it("fills the button once a human override sets the final decision", () => {
    const { include, exclude } = renderRow(makeRow(), { paper_id: "p1", decision: "include" })
    expect(include).toHaveAttribute("aria-pressed", "true")
    expect(include).toHaveAttribute("data-decision-source", "human")
    expect(include.className).toMatch(/bg-intent-success-solid/)
    expect(exclude).toHaveAttribute("aria-pressed", "false")
    expect(exclude.className).not.toMatch(/bg-intent-danger/)
  })

  it("treats a saved human decision as human even without a pending override", () => {
    const { exclude } = renderRow(makeRow({ decided_by: "human_override" }))
    expect(exclude).toHaveAttribute("data-decision-source", "human")
    expect(exclude.className).toMatch(/bg-intent-danger-solid/)
  })
})

describe("ScreeningPaperRow automation removals", () => {
  it("labels the automated step instead of an AI decision", () => {
    renderRow(makeRow({ automation_step: "keyword_ranking", decided_by: "keyword_filter", confidence: null }))
    expect(screen.getByText(/Auto-removed · keyword ranking/)).toBeInTheDocument()
    expect(screen.queryByText(/AI: Exclude/)).not.toBeInTheDocument()
  })
})
