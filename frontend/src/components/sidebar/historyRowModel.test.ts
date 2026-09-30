import { describe, expect, it } from "vitest"
import {
  buildInProgressRowModel,
  buildRunCardModel,
  CONFIG_GENERATING_STALL_MS,
  isConfigGenerationStalled,
  formatCardCost,
  hasFunnelDetail,
  runCardSummary,
  runCardSummaryText,
  truncateTopic,
} from "./historyRowModel"
import type { HistoryEntry } from "@/lib/api"
import type { LiveRun } from "./types"

const baseEntry: HistoryEntry = {
  workflow_id: "wf-1",
  topic: "Test topic",
  status: "stale",
  db_path: "/tmp/runtime.db",
  created_at: "2026-01-01T00:00:00Z",
  papers_found: 10,
  papers_included: 2,
  total_cost: 1.5,
  live_run_id: null,
  notes: null,
}

const liveRun: LiveRun = {
  runId: "run-live",
  topic: "Live topic",
  status: "streaming",
  cost: 0.5,
  workflowId: "wf-1",
  phaseProgress: { value: 0.4, completedPhases: 2 },
  startedAt: "2026-01-01T00:00:00Z",
  papersFound: 20,
  papersIncluded: 5,
}

describe("isConfigGenerationStalled", () => {
  const created = "2026-01-01T00:00:00Z"
  const t0 = Date.parse(created)
  const gen = { ...baseEntry, status: "config_generating", created_at: created, updated_at: null }

  it("flags config_generating with no live stream after an hour", () => {
    expect(isConfigGenerationStalled(gen, false, t0 + CONFIG_GENERATING_STALL_MS + 1)).toBe(true)
    expect(isConfigGenerationStalled(gen, false, t0 + CONFIG_GENERATING_STALL_MS - 1)).toBe(false)
  })

  it("never flags a live stream or another status", () => {
    const late = t0 + 3 * CONFIG_GENERATING_STALL_MS
    expect(isConfigGenerationStalled(gen, true, late)).toBe(false)
    expect(isConfigGenerationStalled({ ...gen, live_run_id: "run-1" }, false, late)).toBe(false)
    expect(isConfigGenerationStalled({ ...gen, status: "config_ready" }, false, late)).toBe(false)
  })

  it("reads SQLite timestamps as UTC", () => {
    const sqlite = { ...gen, created_at: "2026-01-01 00:00:00" }
    expect(isConfigGenerationStalled(sqlite, false, t0 + CONFIG_GENERATING_STALL_MS + 1)).toBe(true)
    expect(isConfigGenerationStalled(sqlite, false, t0 + CONFIG_GENERATING_STALL_MS - 1)).toBe(false)
  })

  it("uses updated_at when present", () => {
    const updated = new Date(t0 + 2 * CONFIG_GENERATING_STALL_MS).toISOString()
    expect(isConfigGenerationStalled({ ...gen, updated_at: updated }, false, t0 + 2.5 * CONFIG_GENERATING_STALL_MS)).toBe(false)
  })

  it("shows Stalled as the card status", () => {
    const model = buildInProgressRowModel(gen, null, null, null, null, {})
    expect(model.statusLabel).toBe("Stalled")
    expect(model.statusKey).toBe("stale")
    expect(model.isResumable).toBe(false)
    expect(buildInProgressRowModel(baseEntry, null, null, null, null, {}).statusLabel).not.toBe("Stalled")
  })
})

describe("buildInProgressRowModel", () => {
  it("marks live row and uses live metrics", () => {
    const entry = { ...baseEntry, live_run_id: "run-live" }
    const model = buildInProgressRowModel(entry, liveRun, "wf-1", null, null, {})
    expect(model.isLiveRow).toBe(true)
    expect(model.rowIsRunning).toBe(true)
    expect(model.papersFound).toBe(20)
    expect(model.cost).toBe(0.5)
    expect(model.isSelected).toBe(true)
    expect(model.variant).toBe("in-progress")
  })

  it("detects reconnecting stale streaming status without live_run_id", () => {
    const entry = { ...baseEntry, status: "streaming", live_run_id: null }
    const model = buildInProgressRowModel(entry, null, null, null, null, {})
    expect(model.isReconnectingRow).toBe(true)
    expect(model.rowIsRunning).toBe(true)
    expect(model.progressValue).toBe(-1)
  })

  it("allows resume for cancelled stale runs when handler provided", () => {
    const entry = { ...baseEntry, status: "cancelled" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {
      onResume: async () => {},
    })
    expect(model.isResumable).toBe(true)
    expect(model.actionPadClass).toBe("pr-14")
  })

  it("labels rows with runStatusLabel and gives a disabled reason", () => {
    const reconnecting = buildInProgressRowModel(
      { ...baseEntry, status: "streaming", live_run_id: null },
      null, null, null, null, {},
    )
    expect(reconnecting.statusLabel).toBe("Reconnecting")
    const noDb = buildInProgressRowModel({ ...baseEntry, db_path: "" }, null, null, null, null, {})
    expect(noDb.canOpen).toBe(false)
    expect(noDb.disabledReason).toBe("No database yet")
  })

  it("uses done progress for terminal history status", () => {
    const entry = { ...baseEntry, status: "completed" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {})
    expect(model.progressValue).toBe(1)
    expect(model.rowIsRunning).toBe(false)
  })

  it("treats awaiting_prospero as parked, not running", () => {
    const entry = { ...baseEntry, status: "awaiting_prospero" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {
      onHideCompleted: async () => {},
    })
    expect(model.statusKey).toBe("awaiting_prospero")
    expect(model.rowIsRunning).toBe(false)
    expect(model.isReconnectingRow).toBe(false)
    expect(model.isCompletedLaneEligible).toBe(false)
    expect(model.progressValue).toBeUndefined()
  })

  it("treats awaiting_review as parked, not running", () => {
    const entry = { ...baseEntry, status: "awaiting_review" }
    const model = buildInProgressRowModel(entry, null, null, null, null, {
      onHideCompleted: async () => {},
    })
    expect(model.statusKey).toBe("awaiting_review")
    expect(model.rowIsRunning).toBe(false)
    expect(model.isCompletedLaneEligible).toBe(false)
  })
})

describe("card metrics", () => {
  it("hides counts until search has found records and cost until spent", () => {
    expect(runCardSummary({ papersFound: 0, papersIncluded: 0, cost: 0 })).toEqual({
      found: null,
      included: null,
      cost: null,
    })
    expect(runCardSummary({ papersFound: 1716, papersIncluded: 6, cost: 1.205 })).toEqual({
      found: 1716,
      included: 6,
      cost: 1.205,
    })
    expect(runCardSummaryText(runCardSummary({ papersFound: 1716, papersIncluded: 6 }))).toBe(
      "1,716 found, 6 included",
    )
    expect(runCardSummaryText(runCardSummary({ papersFound: 40, papersIncluded: null }))).toBe("40 found")
  })

  it("formats card cost to cents without hiding sub-cent spend", () => {
    expect(formatCardCost(1.205)).toBe("$1.21")
    expect(formatCardCost(0.004)).toBe("<$0.01")
  })

  it("offers the full funnel only when it adds stages", () => {
    const stage = (key: string) => ({ key, label: key, count: 1, colorClass: "text-muted" })
    expect(hasFunnelDetail(undefined)).toBe(false)
    expect(hasFunnelDetail([stage("found"), stage("included")])).toBe(false)
    expect(hasFunnelDetail([stage("found"), stage("screened"), stage("included")])).toBe(true)
  })

  it("truncates topics on a word boundary", () => {
    expect(truncateTopic("short")).toBe("short")
    const long = truncateTopic("What hospital-based and hospital-linked models of geriatric care work", 40)
    expect(long.length).toBeLessThanOrEqual(40)
    expect(long.endsWith("…")).toBe(true)
  })
})

describe("buildRunCardModel", () => {
  it("builds live card model from standalone live run", () => {
    const model = buildRunCardModel({
      source: "live",
      liveRun,
      isSelected: true,
      isRunning: true,
    })
    expect(model.variant).toBe("live")
    expect(model.topic).toBe("Live topic")
    expect(model.workflowId).toBe("wf-1")
    expect(model.isSelected).toBe(true)
    expect(model.rowIsRunning).toBe(true)
    expect(model.showNoteField).toBe(false)
    expect(model.showWorkflowBadge).toBe(true)
    expect(model.progressValue).toBe(0.4)
  })

  it("builds completed lane model without progress bar", () => {
    const entry = { ...baseEntry, status: "completed" }
    const model = buildRunCardModel({
      source: "lane",
      entry,
      variant: "completed",
      isSelected: false,
    })
    expect(model.variant).toBe("completed")
    expect(model.showProgressBar).toBe(false)
    expect(model.showWorkflowBadge).toBe(true)
    expect(model.showNoteField).toBe(false)
    expect(model.papersFound).toBe(10)
    expect(model.statusLabel).toBe("Completed")
  })

  it("builds archived lane model with archived card styling", () => {
    const entry = { ...baseEntry, status: "archived" }
    const model = buildRunCardModel({
      source: "lane",
      entry,
      variant: "archived",
      isSelected: true,
    })
    expect(model.variant).toBe("archived")
    expect(model.isSelected).toBe(true)
    expect(model.cardClassName).toContain("sidebar-card-archived")
  })
})
