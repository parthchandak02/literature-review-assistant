import { describe, expect, it } from "vitest"
import { DEMO_WORKFLOW_ID, demoHistoryEntries, demoWorkflowEvents } from "./fixtures"

describe("uiDemo fixtures", () => {
  it("exposes a stable demo workflow id", () => {
    expect(demoHistoryEntries().some((e) => e.workflow_id === DEMO_WORKFLOW_ID)).toBe(true)
  })

  it("includes terminal done events for the demo workflow", () => {
    const events = demoWorkflowEvents(DEMO_WORKFLOW_ID)
    expect(events.some((e) => e.type === "done")).toBe(true)
  })
})
